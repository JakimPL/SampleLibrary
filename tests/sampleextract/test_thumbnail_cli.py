from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from sampleextract.thumbnail_cli import main


def _write_config(tmp_path: Path, database_url: str) -> Path:
    """Points both configured paths at `tmp_path` itself, which always exists -- this CLI only
    ever reads a catalog and audio store an extraction run has already populated.
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
        main([])

    assert raised.value.code == 1
    assert "Configuration error" in capsys.readouterr().err


def test_main_reports_an_empty_catalog(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))

    main([])

    assert "0 samples catalogued: 0 thumbnail(s) computed, 0 already cached." in capsys.readouterr().out


def test_the_force_flag_is_accepted(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))

    main(["--force"])

    assert "0 samples catalogued" in capsys.readouterr().out
