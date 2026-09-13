from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE, DATABASE_URL_ENVIRONMENT_VARIABLE
from sampleserver import cli

PROGRAM = "samplelibrary serve"
PUBLIC_HOST = "0.0.0.0"
OTHER_PORT = 8001
WORKER_COUNT = 4
UNREACHABLE_DATABASE_URL = "postgresql+psycopg://samplelibrary:samplelibrary@localhost:1/samplelibrary"


@dataclass
class RecordedRun:
    calls: list[dict[str, object]] = field(default_factory=list)

    @property
    def only(self) -> dict[str, object]:
        assert len(self.calls) == 1
        return self.calls[0]


def _write_config(tmp_path: Path, *, database_url: str) -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[library]\n"
        f'module_source_directory = "{(tmp_path / "modules").as_posix()}"\n'
        f'library_root = "{(tmp_path / "library").as_posix()}"\n'
        f'database_url = "{database_url}"\n',
        encoding="utf-8",
    )
    return config_path


@pytest.fixture
def recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RecordedRun:
    """Captures what the serve command hands uvicorn, in place of binding a socket, over a catalog that answers."""
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, database_url="unused")))
    monkeypatch.delenv(DATABASE_URL_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.setattr(cli, "open_catalog_connection", lambda database_url: nullcontext())
    run = RecordedRun()
    monkeypatch.setattr(cli.uvicorn, "run", lambda application_path, **options: run.calls.append(options))
    return run


def test_flags_name_the_address_and_the_processes(recorded: RecordedRun) -> None:
    cli.main(["--host", PUBLIC_HOST, "--port", str(OTHER_PORT), "--workers", str(WORKER_COUNT)], prog=PROGRAM)

    options = recorded.only
    assert (options["host"], options["port"], options["workers"]) == (PUBLIC_HOST, OTHER_PORT, WORKER_COUNT)


def test_an_unnamed_process_count_is_left_to_uvicorn(recorded: RecordedRun) -> None:
    """uvicorn reads $WEB_CONCURRENCY only when the count it is handed is absent."""
    cli.main([], prog=PROGRAM)

    assert recorded.only["workers"] is None


def test_reloading_watches_the_source_packages_alone(recorded: RecordedRun) -> None:
    cli.main(["--reload"], prog=PROGRAM)

    options = recorded.only
    assert options["reload"] is True
    assert options["reload_dirs"] == [str(cli.SOURCE_DIRECTORY)]
    assert (cli.SOURCE_DIRECTORY / "sampleserver").is_dir()


def test_reloading_and_several_workers_are_a_usage_error(
    recorded: RecordedRun, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(["--reload", "--workers", str(WORKER_COUNT)], prog=PROGRAM)

    assert raised.value.code == 2
    assert "not allowed with" in capsys.readouterr().err
    assert not recorded.calls


def test_a_missing_configuration_ends_the_start_before_uvicorn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "absent.toml"))
    starts: list[str] = []
    monkeypatch.setattr(cli.uvicorn, "run", lambda application_path, **options: starts.append(application_path))

    with pytest.raises(SystemExit) as raised:
        cli.main([], prog=PROGRAM)

    assert raised.value.code == 1
    assert not starts


def test_an_unreachable_catalog_ends_the_start_before_uvicorn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = _write_config(tmp_path, database_url=UNREACHABLE_DATABASE_URL)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))
    monkeypatch.delenv(DATABASE_URL_ENVIRONMENT_VARIABLE, raising=False)
    starts: list[str] = []
    monkeypatch.setattr(cli.uvicorn, "run", lambda application_path, **options: starts.append(application_path))

    with pytest.raises(SystemExit) as raised:
        cli.main([], prog=PROGRAM)

    assert raised.value.code == 1
    assert "samplelibrary setup database" in capsys.readouterr().err
    assert not starts
