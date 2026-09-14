from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Connection, func, select

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE, DATABASE_URL_ENVIRONMENT_VARIABLE
from samplecore.exit_status import ExitStatus
from samplecore.storage.database import claim_named_lock, named_lock_key
from sampleextract import thumbnail_cli
from samplelibrary.cli import dispatch
from samplelibrary.environment import STEP_LOCK_ENVIRONMENT_VARIABLE
from samplelibrary.step_lock import hold_step_lock

STEP_LOCK_NAME = "samplelibrary-test-library-teacher"


@pytest.fixture(name="configured_step")
def fixture_configured_step(tmp_path: Path, _database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """A config naming this worker's database, and the lock a pipeline would name for a step it starts."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[library]\n"
        f'module_source_directory = "{(tmp_path / "modules").as_posix()}"\n'
        f'library_root = "{(tmp_path / "library").as_posix()}"\n'
        f'database_url = "{_database_url}"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))
    monkeypatch.delenv(DATABASE_URL_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.setenv(STEP_LOCK_ENVIRONMENT_VARIABLE, STEP_LOCK_NAME)
    return STEP_LOCK_NAME


def _release(connection: Connection, name: str) -> None:
    connection.execute(select(func.pg_advisory_unlock(named_lock_key(name))))


def test_a_process_named_no_lock_takes_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(STEP_LOCK_ENVIRONMENT_VARIABLE, raising=False)

    assert hold_step_lock() is None


def test_a_step_holds_its_lock_until_its_connection_closes(connection: Connection, configured_step: str) -> None:
    held = hold_step_lock()

    assert held is not None
    assert not claim_named_lock(connection, configured_step)
    held.close()
    assert claim_named_lock(connection, configured_step)
    _release(connection, configured_step)


def test_a_step_whose_lock_another_process_holds_runs_nothing(connection: Connection, configured_step: str) -> None:
    assert claim_named_lock(connection, configured_step)

    with pytest.raises(SystemExit) as raised:
        hold_step_lock()

    assert raised.value.code == ExitStatus.REFUSED
    _release(connection, configured_step)


def test_the_dispatcher_holds_the_named_lock_for_as_long_as_the_command_runs(
    connection: Connection, configured_step: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_free_while_running: list[bool] = []

    def run(argv: list[str], *, prog: str) -> None:
        lock_free_while_running.append(claim_named_lock(connection, configured_step))

    monkeypatch.setattr(thumbnail_cli, "main", run)

    dispatch(["thumbnails"])

    assert lock_free_while_running == [False]
    assert claim_named_lock(connection, configured_step)
    _release(connection, configured_step)
