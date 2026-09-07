from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from sampleextract.notes.cli import main


def _write_config(tmp_path: Path, database_url: str) -> Path:
    module_source_directory = tmp_path / "modules"
    module_source_directory.mkdir()
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[library]\n"
        f'module_source_directory = "{module_source_directory.as_posix()}"\n'
        f'library_root = "{(tmp_path / "library").as_posix()}"\n'
        f'database_url = "{database_url}"\n',
        encoding="utf-8",
    )
    return config_path


def test_main_reports_an_empty_corpus(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))

    main([])

    assert "Discovered 0 modules" in capsys.readouterr().out


def test_main_passes_over_a_file_the_catalog_never_ingested(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    xm_module_bytes: bytes,
) -> None:
    """This pass attaches notes to modules the catalog already holds, so an unknown file is counted only."""
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    (tmp_path / "modules" / "song.xm").write_bytes(xm_module_bytes)

    main([])

    assert "Discovered 1 modules: 0 read" in capsys.readouterr().out
