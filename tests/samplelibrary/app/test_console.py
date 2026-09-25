from __future__ import annotations

import sys
from pathlib import Path

import pytest

from samplelibrary.app import console
from samplelibrary.app.console import log_without_console
from samplelibrary.paths import APPLICATION_LOG_NAME, PREVIOUS_APPLICATION_LOG_NAME


@pytest.fixture(name="log_directory")
def fixture_log_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "logs"
    monkeypatch.setattr(console, "application_log_directory", lambda: directory)
    return directory


def test_a_windowless_start_writes_its_output_to_the_log_and_keeps_the_previous_one(
    log_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_directory.mkdir()
    (log_directory / APPLICATION_LOG_NAME).write_text("last session\n", encoding="utf-8")
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    path = log_without_console()
    print("this session")
    sys.stderr.write("its warning\n")
    sys.stdout.close()

    assert path == log_directory / APPLICATION_LOG_NAME
    assert path.read_text(encoding="utf-8") == "this session\nits warning\n"
    assert (log_directory / PREVIOUS_APPLICATION_LOG_NAME).read_text(encoding="utf-8") == "last session\n"


def test_a_start_in_a_console_keeps_writing_to_it(log_directory: Path) -> None:
    streams = (sys.stdout, sys.stderr)

    assert log_without_console() is None
    assert (sys.stdout, sys.stderr) == streams
    assert not log_directory.exists()
