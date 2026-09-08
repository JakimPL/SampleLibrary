from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from sampleextract.cli import main


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


def test_main_reports_a_configuration_error_and_exits_without_a_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "does-not-exist.toml"))

    with pytest.raises(SystemExit) as raised:
        main([])

    assert raised.value.code == 1
    assert "Configuration error" in capsys.readouterr().err


def test_main_creates_the_library_root_and_reports_an_empty_corpus(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))

    main([])

    assert (tmp_path / "library").is_dir()
    assert "Discovered 0 modules" in capsys.readouterr().out


def test_main_warns_about_an_unreadable_file_and_still_finishes(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A collection holding a file the parsers cannot read is a standing fact, not a failed run.

    The stages after extraction depend on it finishing, so a corpus this pass could read none of
    still leaves the command a success and the reason on stderr.
    """
    config_path = _write_config(tmp_path, _database_url)
    (tmp_path / "modules" / "corrupt.xm").write_bytes(b"not a real module file")
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))

    main([])

    output = capsys.readouterr()
    assert "corrupt.xm" in output.err
    assert "1 unreadable" in output.out


def test_main_ingests_every_module_the_source_directory_holds(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    xm_module_bytes: bytes,
    it_module_bytes: bytes,
) -> None:
    config_path = _write_config(tmp_path, _database_url)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))
    source = tmp_path / "modules"
    (source / "first.xm").write_bytes(xm_module_bytes)
    (source / "second.it").write_bytes(it_module_bytes)

    main([])

    assert "Discovered 2 modules: 2 ingested" in capsys.readouterr().out


def test_main_refuses_a_worker_count_below_one() -> None:
    """A run spends at least one process, so a count under that is a typo worth stopping for."""
    with pytest.raises(SystemExit) as exit_info:
        main(["--workers", "0"])

    assert exit_info.value.code == 2


def test_main_refuses_a_worker_count_that_is_not_a_whole_number() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--workers", "many"])

    assert exit_info.value.code == 2
