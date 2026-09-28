from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from samplecore.exit_status import ExitStatus
from samplecore.storage.repositories.module_link import PostgresModuleLinkRepository
from sampleextract.links.cli import main
from tests.sampleextract.links.conftest import catalog_module_file, write_links

PROGRAM = "sampleripper links import"
A_PAGE = "https://www.modules.pl/?id=module&mod=1"


def _write_config(tmp_path: Path, database_url: str, *, collection: Path | None) -> Path:
    config_path = tmp_path / "config.toml"
    sources = f'module_source_directory = "{collection.as_posix()}"\n' if collection is not None else ""
    config_path.write_text(
        f"[library]\n{sources}"
        f'library_root = "{(tmp_path / "library").as_posix()}"\n'
        f'database_url = "{database_url}"\n',
        encoding="utf-8",
    )
    return config_path


@pytest.fixture
def configured(tmp_path: Path, collection: Path, _database_url: str, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(
        CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url, collection=collection))
    )
    return tmp_path / "links.csv"


def test_the_command_records_the_links_of_the_file_it_is_given(
    connection: Connection, collection: Path, configured: Path, xm_module_bytes: bytes
) -> None:
    module = catalog_module_file(connection, collection, "XM/song.xm", xm_module_bytes)
    write_links(configured, (("XM/song.xm", A_PAGE),))

    main([str(configured)], prog=PROGRAM)

    assert PostgresModuleLinkRepository(connection).get_many([module.hash])[module.hash].url == A_PAGE


def test_a_file_naming_files_that_are_not_there_ends_normally(
    connection: Connection, configured: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_links(configured, (("XM/absent.xm", A_PAGE),))

    main([str(configured)], prog=PROGRAM)

    assert "XM/absent.xm" in capsys.readouterr().err
    assert PostgresModuleLinkRepository(connection).count() == 0


def test_a_library_without_a_module_collection_is_refused(
    tmp_path: Path, _database_url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url, collection=None)))
    path = write_links(tmp_path / "links.csv", (("XM/song.xm", A_PAGE),))

    with pytest.raises(SystemExit) as raised:
        main([str(path)], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED
    assert "module_source_directory" in capsys.readouterr().err


def test_a_file_that_is_not_there_ends_with_one_message(
    configured: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    absent = tmp_path / "absent.csv"

    with pytest.raises(SystemExit) as raised:
        main([str(absent)], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED
    reported = capsys.readouterr().err
    assert str(absent) in reported
    assert "Traceback" not in reported
