from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.repositories.sample import PostgresSampleRepository
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

    assert raised.value.code == 1
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
