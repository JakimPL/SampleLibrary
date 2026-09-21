from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from samplecore.exit_status import ExitStatus
from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.repositories.sample import PostgresSampleRepository
from sampleextract.cli import main as extract_main
from sampleextract.equivalence.cli import main

PROGRAM = "samplelibrary equivalence"
SAMPLE_HASH = "a" * 64
OTHER_SAMPLE_HASH = "b" * 64


def _write_config(tmp_path: Path, database_url: str) -> Path:
    """Points both configured paths at `tmp_path` itself, which always exists -- unlike the
    extraction CLI, this one never creates directories, since it only ever reads a catalog and
    audio store an extraction run has already populated.
    """
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[library]\nmodule_source_directory = "{tmp_path.as_posix()}"\nlibrary_root = "{tmp_path.as_posix()}"\n'
        f'database_url = "{database_url}"\n',
        encoding="utf-8",
    )
    return config_path


def test_main_reports_a_configuration_error_and_exits_without_a_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "does-not-exist.toml"))

    with pytest.raises(SystemExit) as raised:
        main([], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED
    assert "Configuration error" in capsys.readouterr().err


def test_main_reports_an_empty_catalog(
    _database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))

    main([], prog=PROGRAM)

    assert "Considered 0 samples" in capsys.readouterr().out


def test_main_passes_the_limit_argument_through(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    repository = PostgresSampleRepository(connection)
    for sample_hash in (SAMPLE_HASH, OTHER_SAMPLE_HASH):
        sample = Sample(hash=sample_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
        repository.upsert(sample)
        audio_store.write(tmp_path, SamplePCM(sample=sample, pcm=np.zeros((8, 1))))
    connection.commit()

    main(["--limit", "1"], prog=PROGRAM)

    assert "Considered 1 samples" in capsys.readouterr().out


def test_a_limit_below_one_sample_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--limit", "0"], prog=PROGRAM)

    assert raised.value.code == 2


NOTHING_TO_DETECT = "nothing to detect"


def test_a_pass_over_the_samples_the_last_complete_pass_compared_ends_at_once(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    xm_module_bytes: bytes,
    mod_module_bytes: bytes,
) -> None:
    """A module holding only samples the catalog has already leaves the readable samples, and the relations, as they were."""
    modules = tmp_path / "modules"
    modules.mkdir()
    (modules / "song.xm").write_bytes(xm_module_bytes)
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[library]\nmodule_source_directory = "{modules.as_posix()}"\nlibrary_root = "{tmp_path.as_posix()}"\n'
        f'database_url = "{_database_url}"\nminimum_sample_frames = 16\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))
    extract_main(["--workers", "1"], prog="samplelibrary extract")

    main(["--limit", "1"], prog=PROGRAM)
    main([], prog=PROGRAM)
    assert NOTHING_TO_DETECT not in capsys.readouterr().out

    main([], prog=PROGRAM)
    assert NOTHING_TO_DETECT in capsys.readouterr().out

    main(["--force"], prog=PROGRAM)
    assert NOTHING_TO_DETECT not in capsys.readouterr().out

    (modules / "eight-bit.mod").write_bytes(mod_module_bytes)
    extract_main(["--workers", "1"], prog="samplelibrary extract")
    capsys.readouterr()
    main([], prog=PROGRAM)
    assert NOTHING_TO_DETECT not in capsys.readouterr().out
