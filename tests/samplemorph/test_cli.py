from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth
from trackmod.trackers.xm.tuning import Tuning

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from samplecore.exit_status import ExitStatus
from samplecore.models.channels import ChannelLayout
from samplecore.models.module import Module
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.models.sample_properties import SampleOccurrence, XMSampleProperties
from samplecore.models.tracker import TrackerFormat
from samplecore.storage import audio_store
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository
from samplemorph.cli import MorphCommand, main
from samplemorph.envelope.payload import response_from_payload
from samplemorph.envelope.response import HeldEnd
from samplemorph.envelope.settings import EnvelopeSettings
from tests.samplemorph.conftest import harmonic_tone

PROGRAM = "samplelibrary morph"
SAMPLE_FRAME_COUNT = 4096
CATALOG_SIZE = 12
SAMPLE_RATE_HZ = 8_363


def _write_config(tmp_path: Path, database_url: str) -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[library]\nmodule_source_directory = "{tmp_path.as_posix()}"\n'
        f'library_root = "{tmp_path.as_posix()}"\ndatabase_url = "{database_url}"\n',
        encoding="utf-8",
    )
    return config_path


def _seed_catalog(connection: Connection, library_root: Path) -> list[str]:
    """A small catalog of distinct tones, each with one occurrence naming its playback rate.

    A hash repeats one byte, so the prefixes that name files and folders differ between samples.
    """
    module_repository = PostgresModuleRepository(connection)
    hashes = []
    for index in range(CATALOG_SIZE):
        sample = Sample(
            hash=f"{index + 1:02x}" * 32,
            depth=BitDepth.SIXTEEN,
            channels=ChannelLayout.MONO,
            frames=SAMPLE_FRAME_COUNT,
        )
        PostgresSampleRepository(connection).upsert(sample)
        audio_store.write(
            library_root,
            SamplePCM(sample=sample, pcm=harmonic_tone(SAMPLE_FRAME_COUNT, frequency=110.0 * (1.0 + index / 3.0))),
        )
        module = Module(
            id=module_repository.next_id(),
            hash=format(index + 900, "064x"),
            filename=f"song{index}.xm",
            tracker=TrackerFormat.XM,
            title="untitled",
            channel_count=4,
            pattern_count=1,
            instrument_count=1,
            sample_count=1,
            file_size=1024,
            ingested_at=datetime.now(UTC),
        )
        module_repository.insert(module)
        PostgresSamplePropertiesRepository(connection).upsert(
            XMSampleProperties(
                sample_hash=sample.hash,
                occurrence=SampleOccurrence(module_hash=module.hash, instrument_index=0, sample_slot=0),
                name=f"tone{index}",
                rate=SAMPLE_RATE_HZ,
                volume=64,
                tuning=Tuning(relative_note=0, finetune=0),
            )
        )
        hashes.append(sample.hash)
    connection.commit()
    return hashes


def test_main_reports_a_configuration_error_and_exits_without_a_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "does-not-exist.toml"))

    with pytest.raises(SystemExit) as raised:
        main([MorphCommand.SERVE], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED
    assert "Configuration error" in capsys.readouterr().err


def test_the_renderer_and_the_filter_commands_load_no_training_library() -> None:
    """Every morph command's flags, and the service they start, are read with the training stack left unloaded."""
    probe = (
        "import sys, samplemorph.cli, samplemorph.service.app; "
        "loaded = ('torch', 'lightning', 'mlflow', 'sklearn', 'threadpoolctl', 'pyloudnorm', 'sampledescriptor'); "
        "sys.exit(any(name.split('.')[0] in loaded for name in sys.modules))"
    )

    finished = subprocess.run(
        [sys.executable, "-c", probe], env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, check=False
    )

    assert finished.returncode == 0


def test_a_response_is_written_as_the_filter_between_two_samples(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hashes = _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    selection = tmp_path / "morph.yaml"
    selection.write_text("envelope:\n  excitation: first\n", encoding="utf-8")
    output = tmp_path / "response.bin"

    main(
        [
            "response",
            "--first",
            hashes[0],
            "--second",
            hashes[-1],
            "--selection",
            str(selection),
            "--output",
            str(output),
        ],
        prog=PROGRAM,
    )

    response = response_from_payload(output.read_bytes())
    assert response.description.coefficient_count == EnvelopeSettings().coefficient_count
    assert response.first.held is HeldEnd.FIRST
    assert response.second.held is HeldEnd.SECOND
    assert response.first.coefficients.shape[1] == response.first.description.frame_count


def test_a_response_asked_for_under_a_gliding_route_says_so(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    hashes = _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    selection = tmp_path / "morph.yaml"
    selection.write_text("glide: subharmonic\n", encoding="utf-8")

    with pytest.raises(SystemExit) as raised:
        main(
            [
                "response",
                "--first",
                hashes[0],
                "--second",
                hashes[-1],
                "--selection",
                str(selection),
                "--output",
                str(tmp_path / "response.bin"),
            ],
            prog=PROGRAM,
        )

    assert raised.value.code == ExitStatus.REFUSED
    assert "glides by subharmonic" in capsys.readouterr().err


def test_a_response_asked_for_under_a_selection_this_pipeline_cannot_read_says_so(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    hashes = _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    selection = tmp_path / "morph.yaml"
    selection.write_text("route: transport\n", encoding="utf-8")

    with pytest.raises(SystemExit) as raised:
        main(
            [
                "response",
                "--first",
                hashes[0],
                "--second",
                hashes[-1],
                "--selection",
                str(selection),
                "--output",
                str(tmp_path / "response.bin"),
            ],
            prog=PROGRAM,
        )

    assert raised.value.code == ExitStatus.REFUSED
    assert "Wrote nothing:" in capsys.readouterr().err
