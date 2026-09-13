from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from samplecore.tracking.store import tracking_uri
from samplelibrary.tracking import ui

PROGRAM = "samplelibrary tracking ui"
CHOSEN_PORT = 5123
INTERFACE_EXIT_STATUS = 3


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[library]\n"
        f'module_source_directory = "{(tmp_path / "modules").as_posix()}"\n'
        f'library_root = "{(tmp_path / "library").as_posix()}"\n'
        'database_url = "postgresql+psycopg://user:pass@host/db"\n',
        encoding="utf-8",
    )
    return config_path


def test_the_interface_serves_the_configured_run_store_on_the_chosen_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path)))
    launched: list[list[str]] = []

    def launch(command: list[str], *, check: bool) -> subprocess.CompletedProcess[bytes]:
        launched.append(command)
        return subprocess.CompletedProcess(command, INTERFACE_EXIT_STATUS)

    monkeypatch.setattr(ui.subprocess, "run", launch)

    with pytest.raises(SystemExit) as raised:
        ui.main(["--port", str(CHOSEN_PORT)], prog=PROGRAM)

    assert raised.value.code == INTERFACE_EXIT_STATUS
    assert launched == [ui.interface_command(tracking_uri(tmp_path / "library"), port=CHOSEN_PORT)]


def test_the_interface_command_names_the_store_the_host_and_the_port() -> None:
    command = ui.interface_command("sqlite:///store.db", port=CHOSEN_PORT)

    assert command[command.index("--backend-store-uri") + 1] == "sqlite:///store.db"
    assert command[command.index("--host") + 1] == ui.LOCAL_HOST
    assert command[command.index("--port") + 1] == str(CHOSEN_PORT)


def test_a_missing_configuration_ends_the_process_before_the_interface_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "absent.toml"))
    launched: list[list[str]] = []
    monkeypatch.setattr(ui.subprocess, "run", lambda command, *, check: launched.append(command))

    with pytest.raises(SystemExit) as raised:
        ui.main([], prog=PROGRAM)

    assert raised.value.code == 1
    assert not launched
