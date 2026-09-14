from __future__ import annotations

import signal
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from samplecore.exit_status import ExitStatus
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


@dataclass
class FakeInterface:
    """Stands in for MLflow's process: records how it was started and every signal handed to it."""

    commands: list[list[str]] = field(default_factory=list)
    signals: list[int] = field(default_factory=list)
    terminate_while_waiting: bool = False

    def start(self, command: list[str]) -> FakeInterface:
        self.commands.append(command)
        return self

    def send_signal(self, signal_number: int) -> None:
        self.signals.append(signal_number)

    def wait(self) -> int:
        if self.terminate_while_waiting:
            signal.raise_signal(signal.SIGTERM)
        return INTERFACE_EXIT_STATUS

    def __enter__(self) -> FakeInterface:
        return self

    def __exit__(self, *_: object) -> None:
        return None


@pytest.fixture
def interface(monkeypatch: pytest.MonkeyPatch) -> FakeInterface:
    fake = FakeInterface()
    monkeypatch.setattr(ui.subprocess, "Popen", fake.start)
    return fake


def test_the_interface_serves_the_configured_run_store_on_the_chosen_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interface: FakeInterface
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path)))

    with pytest.raises(SystemExit) as raised:
        ui.main(["--port", str(CHOSEN_PORT)], prog=PROGRAM)

    assert raised.value.code == INTERFACE_EXIT_STATUS
    assert interface.commands == [ui.interface_command(tracking_uri(tmp_path / "library"), port=CHOSEN_PORT)]


def test_a_termination_request_is_handed_on_to_the_interface(interface: FakeInterface) -> None:
    interface.terminate_while_waiting = True
    handler_before = signal.getsignal(signal.SIGTERM)

    status = ui.run_interface(["mlflow"])

    assert status == INTERFACE_EXIT_STATUS
    assert interface.signals == [signal.SIGTERM]
    assert signal.getsignal(signal.SIGTERM) == handler_before


def test_the_interface_command_names_the_store_the_host_and_the_port() -> None:
    command = ui.interface_command("sqlite:///store.db", port=CHOSEN_PORT)

    assert command[command.index("--backend-store-uri") + 1] == "sqlite:///store.db"
    assert command[command.index("--host") + 1] == ui.LOCAL_HOST
    assert command[command.index("--port") + 1] == str(CHOSEN_PORT)


def test_a_missing_configuration_ends_the_process_before_the_interface_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interface: FakeInterface
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "absent.toml"))

    with pytest.raises(SystemExit) as raised:
        ui.main([], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED
    assert not interface.commands
