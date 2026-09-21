from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from samplecore.exit_status import ExitStatus
from samplecore.storage.repositories.module import PostgresModuleRepository
from sampleextract.cli import main

PROGRAM = "samplelibrary extract"


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
        main([], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED
    assert "Configuration error" in capsys.readouterr().err


def test_main_creates_the_library_root_and_reports_an_empty_corpus(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))

    main([], prog=PROGRAM)

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

    main([], prog=PROGRAM)

    output = capsys.readouterr()
    assert "Could not parse" in output.err
    assert "corrupt.xm" in output.err
    assert "1 failed" in output.out


def test_a_missing_source_directory_ends_the_command_with_one_message(
    _database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = _write_config(tmp_path, _database_url)
    (tmp_path / "modules").rmdir()
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))

    with pytest.raises(SystemExit) as raised:
        main([], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED
    assert "does not exist" in capsys.readouterr().err


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

    main([], prog=PROGRAM)

    assert "Discovered 2 modules: 2 ingested" in capsys.readouterr().out


def test_main_refuses_a_worker_count_below_one() -> None:
    """A run spends at least one process, so a count under that is a typo worth stopping for."""
    with pytest.raises(SystemExit) as exit_info:
        main(["--workers", "0"], prog=PROGRAM)

    assert exit_info.value.code == 2


def test_main_refuses_a_worker_count_that_is_not_a_whole_number() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--workers", "many"], prog=PROGRAM)

    assert exit_info.value.code == 2


def test_pruning_after_a_pass_removes_a_module_whose_file_is_gone(
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
    main([], prog=PROGRAM)
    (source / "second.it").unlink()

    main(["--prune"], prog=PROGRAM)

    assert "Pruned 1 module(s)" in capsys.readouterr().out
    assert [stored.filename for stored in PostgresModuleRepository(connection).list_all()] == ["first.xm"]


def test_pruning_is_refused_when_the_source_directory_holds_no_module_at_all(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    xm_module_bytes: bytes,
) -> None:
    """An unmounted drive leaves an empty folder behind, which must not read as a collection deleted."""
    config_path = _write_config(tmp_path, _database_url)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))
    (tmp_path / "modules" / "first.xm").write_bytes(xm_module_bytes)
    main([], prog=PROGRAM)
    (tmp_path / "modules" / "first.xm").unlink()

    with pytest.raises(SystemExit) as raised:
        main(["--prune"], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED
    assert "Pruned nothing" in capsys.readouterr().err
    assert len(PostgresModuleRepository(connection).list_all()) == 1


NOTHING_TO_EXTRACT = "nothing to extract"


def _two_module_collection(tmp_path: Path, xm_module_bytes: bytes, it_module_bytes: bytes) -> Path:
    source = tmp_path / "modules"
    (source / "first.xm").write_bytes(xm_module_bytes)
    (source / "second.it").write_bytes(it_module_bytes)
    return source


def test_a_pruned_pass_over_an_unchanged_collection_is_not_read_again(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    xm_module_bytes: bytes,
    it_module_bytes: bytes,
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    _two_module_collection(tmp_path, xm_module_bytes, it_module_bytes)
    main(["--prune", "--workers", "1"], prog=PROGRAM)
    capsys.readouterr()

    main(["--prune", "--workers", "1"], prog=PROGRAM)

    assert NOTHING_TO_EXTRACT in capsys.readouterr().out


def test_a_pass_without_a_prune_leaves_the_collection_to_be_read_again(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    xm_module_bytes: bytes,
    it_module_bytes: bytes,
) -> None:
    """Only a pruned pass leaves a catalog mirroring the collection, so only it lets the next pass end at once."""
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    _two_module_collection(tmp_path, xm_module_bytes, it_module_bytes)
    main(["--workers", "1"], prog=PROGRAM)
    capsys.readouterr()

    main(["--prune", "--workers", "1"], prog=PROGRAM)

    assert NOTHING_TO_EXTRACT not in capsys.readouterr().out


def test_a_collection_changed_since_the_pruned_pass_is_read_again(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    xm_module_bytes: bytes,
    it_module_bytes: bytes,
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    source = _two_module_collection(tmp_path, xm_module_bytes, it_module_bytes)
    main(["--prune", "--workers", "1"], prog=PROGRAM)
    (source / "second.it").unlink()
    capsys.readouterr()

    main(["--prune", "--workers", "1"], prog=PROGRAM)

    output = capsys.readouterr().out
    assert NOTHING_TO_EXTRACT not in output
    assert "Pruned 1 module(s)" in output
    assert len(PostgresModuleRepository(connection).list_all()) == 1


def test_forcing_a_pass_reads_a_collection_its_last_pruned_pass_left_unchanged(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    xm_module_bytes: bytes,
    it_module_bytes: bytes,
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    _two_module_collection(tmp_path, xm_module_bytes, it_module_bytes)
    main(["--prune", "--workers", "1"], prog=PROGRAM)
    capsys.readouterr()

    main(["--prune", "--force", "--workers", "1"], prog=PROGRAM)

    output = capsys.readouterr().out
    assert NOTHING_TO_EXTRACT not in output
    assert "2 already known" in output
