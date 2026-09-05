from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from trackmod.core.samples.depth import BitDepth

from samplecloud.cli import main
from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE, DEFAULT_DATABASE_FILENAME
from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.database import connect
from samplecore.storage.repositories.sample import DuckDBSampleRepository

SAMPLE_HASH = "a" * 64


def _write_config(tmp_path: Path) -> Path:
    """Points both configured paths at `tmp_path` itself, which always exists -- this CLI only
    ever reads a catalog and audio store an extraction run has already populated.
    """
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[library]\nmodule_source_directory = "{tmp_path.as_posix()}"\nlibrary_root = "{tmp_path.as_posix()}"\n',
        encoding="utf-8",
    )
    return config_path


def test_main_reports_a_configuration_error_and_exits_without_a_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "does-not-exist.toml"))

    with pytest.raises(SystemExit) as raised:
        main([])

    assert raised.value.code == 1
    assert "Configuration error" in capsys.readouterr().err


def test_main_reports_an_empty_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path)))

    main([])

    output = capsys.readouterr().out
    assert "Extracted features for 0 new samples" in output
    assert "Reduced 0 samples" in output


def test_main_passes_the_limit_argument_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path)))
    connection = connect(tmp_path / DEFAULT_DATABASE_FILENAME)
    sample = Sample(hash=SAMPLE_HASH, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=32)
    DuckDBSampleRepository(connection).upsert(sample)
    audio_store.write(tmp_path, SamplePCM(sample=sample, pcm=np.zeros((32, 1))))
    connection.close()

    main(["--limit", "0"])

    assert "Extracted features for 0 new samples" in capsys.readouterr().out
