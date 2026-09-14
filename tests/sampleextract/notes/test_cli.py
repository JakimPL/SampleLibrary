from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from sampleextract.cli import main as extract_main
from sampleextract.notes.cli import main

PROGRAM = "samplelibrary notes"


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

    main([], prog=PROGRAM)

    assert "Discovered 0 files" in capsys.readouterr().out


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

    main([], prog=PROGRAM)

    assert "Discovered 1 files: 0 module(s) read" in capsys.readouterr().out


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="file modes bar reading only for other users")
def test_a_file_the_pass_cannot_read_is_a_warning_and_the_pass_still_succeeds(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    xm_module_bytes: bytes,
) -> None:
    """An unreadable file describes the collection, so the notes of everything else still land."""
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    unreadable = tmp_path / "modules" / "locked.xm"
    unreadable.write_bytes(xm_module_bytes)
    unreadable.chmod(0)

    main([], prog=PROGRAM)

    captured = capsys.readouterr()
    assert "1 failed" in captured.out
    assert "Could not read" in captured.err


NOTHING_TO_READ = "nothing to read"


def test_a_pass_over_the_modules_the_last_complete_pass_read_ends_at_once(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    xm_module_bytes: bytes,
    it_module_bytes: bytes,
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    (tmp_path / "modules" / "song.xm").write_bytes(xm_module_bytes)
    extract_main(["--workers", "1"], prog="samplelibrary extract")
    main([], prog=PROGRAM)
    capsys.readouterr()

    main([], prog=PROGRAM)
    assert NOTHING_TO_READ in capsys.readouterr().out

    (tmp_path / "modules" / "other.it").write_bytes(it_module_bytes)
    extract_main(["--workers", "1"], prog="samplelibrary extract")
    capsys.readouterr()
    main([], prog=PROGRAM)
    assert NOTHING_TO_READ not in capsys.readouterr().out

    main(["--force"], prog=PROGRAM)
    assert "2 module(s) read" in capsys.readouterr().out
