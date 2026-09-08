from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import soundfile
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth
from trackmod.trackers.xm.tuning import Tuning

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
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
from samplemorph.cli import main
from samplemorph.model_store import model_path
from tests.samplemorph.conftest import harmonic_tone

SAMPLE_FRAME_COUNT = 4096
CATALOG_SIZE = 12
LATENT_SIZE = 4
SAMPLE_RATE_HZ = 8_363
MODEL_NAME = "under-test"


def _write_config(tmp_path: Path, database_url: str) -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[library]\nmodule_source_directory = "{tmp_path.as_posix()}"\n'
        f'library_root = "{tmp_path.as_posix()}"\ndatabase_url = "{database_url}"\n',
        encoding="utf-8",
    )
    return config_path


def _seed_catalog(connection: Connection, library_root: Path) -> list[str]:
    """A small catalog of distinct tones, each with one occurrence naming its playback rate."""
    module_repository = PostgresModuleRepository(connection)
    hashes = []
    for index in range(CATALOG_SIZE):
        sample = Sample(
            hash=format(index + 1, "064x"),
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
        main(["fit"])

    assert raised.value.code == 1
    assert "Configuration error" in capsys.readouterr().err


def test_an_unknown_canonicalizer_exits_before_the_catalog_is_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Argument parsing runs first, so a bad flag never reaches the database."""
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "does-not-exist.toml"))

    with pytest.raises(SystemExit) as raised:
        main(["fit", "--canonicalizer", "stargazer"])

    assert raised.value.code == 2


def test_fitting_writes_a_model_under_the_library_root(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))

    main(["fit", "--canonicalizer", "mel", "--latent-size", str(LATENT_SIZE), "--model", MODEL_NAME])

    assert model_path(tmp_path, name=MODEL_NAME).exists()
    assert "Fitted" in capsys.readouterr().out


def test_rendering_writes_a_listening_set_through_a_fitted_model(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hashes = _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    main(["fit", "--canonicalizer", "mel", "--latent-size", str(LATENT_SIZE), "--model", MODEL_NAME])
    output = tmp_path / "render"

    main(
        [
            "render",
            "--first",
            hashes[0],
            "--second",
            hashes[-1],
            "--model",
            MODEL_NAME,
            "--output",
            str(output),
        ]
    )

    written = sorted(path.name for path in output.glob("*.wav"))
    assert written == [
        "morph_025.wav",
        "morph_050.wav",
        "morph_075.wav",
        "original_first.wav",
        "original_second.wav",
        "reconstruction_first.wav",
        "reconstruction_second.wav",
    ]
    assert (output / "manifest.json").exists()
    assert soundfile.info(output / "original_first.wav").samplerate == SAMPLE_RATE_HZ


def test_rendering_a_sample_the_catalog_lacks_says_so(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hashes = _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    main(["fit", "--canonicalizer", "mel", "--latent-size", str(LATENT_SIZE), "--model", MODEL_NAME])

    with pytest.raises(ValueError, match="holds no sample"):
        main(
            [
                "render",
                "--first",
                hashes[0],
                "--second",
                "f" * 64,
                "--model",
                MODEL_NAME,
                "--output",
                str(tmp_path / "render"),
            ]
        )
