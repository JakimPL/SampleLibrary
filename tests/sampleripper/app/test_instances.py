from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import httpx
import pytest

from sampleripper.app.instance import place
from sampleripper.app.instance.place import InstancePlace, instance_place
from sampleripper.app.instance.record import InstanceRecord, read_record
from sampleripper.paths import instances_directory

START_SECONDS: Final[float] = 60.0
TAKEOVER_SECONDS: Final[float] = 120.0
POLL_SECONDS: Final[float] = 0.2


@dataclass(frozen=True)
class AppWorld:
    """A config no one has written yet, a state folder of its own, and a free port for the application."""

    environment: dict[str, str]
    place: InstancePlace
    port: int

    def command(self, *options: str) -> list[str]:
        return [sys.executable, "-m", "sampleripper.app", "--port", str(self.port), "--no-browser", *options]

    def start(self) -> subprocess.Popen[bytes]:
        return subprocess.Popen(  # pylint: disable=consider-using-with
            self.command(), env=self.environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    def run(self, *options: str) -> int:
        return subprocess.run(
            self.command(*options), env=self.environment, capture_output=True, check=False, timeout=TAKEOVER_SECONDS
        ).returncode

    def answering_record(self, *, other_than: InstanceRecord | None, seconds: float) -> InstanceRecord:
        """The record of an application that answers, once one other than ``other_than`` does."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            record = read_record(self.place.record)
            if record is not None and record != other_than and _answers(record):
                return record
            time.sleep(POLL_SECONDS)
        raise AssertionError("no application answered in time")


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[AppWorld]:
    config_path = tmp_path / "settings" / "config.toml"
    monkeypatch.setenv("SAMPLERIPPER_CONFIG", str(config_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(place, "instances_directory", instances_directory)
    with socket.create_server(("127.0.0.1", 0)) as probe:
        port: int = probe.getsockname()[1]
    yield AppWorld(environment=dict(os.environ), place=instance_place(config_path), port=port)


@pytest.fixture
def first(world: AppWorld) -> Iterator[subprocess.Popen[bytes]]:
    application = world.start()
    yield application
    if application.poll() is None:
        application.kill()
    application.wait()


def _answers(record: InstanceRecord) -> bool:
    try:
        return httpx.get(f"{record.address}api/setup/installation", timeout=2.0).is_success
    except httpx.HTTPError:
        return False


def test_a_second_start_opens_the_running_application_and_quit_ends_it(
    world: AppWorld, first: subprocess.Popen[bytes]
) -> None:
    record = world.answering_record(other_than=None, seconds=START_SECONDS)

    assert world.run() == 0
    assert first.poll() is None
    assert read_record(world.place.record) == record

    assert world.run("--quit") == 0
    assert first.wait(timeout=START_SECONDS) == 0


@pytest.mark.skipif(sys.platform == "win32", reason="stopping a process takes a POSIX signal")
def test_an_application_that_stopped_answering_is_ended_and_replaced(
    world: AppWorld, first: subprocess.Popen[bytes]
) -> None:
    stopped = world.answering_record(other_than=None, seconds=START_SECONDS)
    os.kill(first.pid, signal.SIGSTOP)

    replacement = world.start()
    try:
        replacing = world.answering_record(other_than=stopped, seconds=TAKEOVER_SECONDS)

        assert first.wait(timeout=START_SECONDS) == -signal.SIGKILL
        assert replacing.process.pid == replacement.pid
    finally:
        assert world.run("--quit") == 0
        replacement.wait(timeout=START_SECONDS)
