from __future__ import annotations

import sys
from pathlib import Path

import pytest

from sampleripper.app.console import console_log


def test_a_windowless_start_writes_its_output_to_the_log_and_keeps_the_previous_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "logs" / "app-key.log"
    previous = tmp_path / "logs" / "app-key.previous.log"
    log.parent.mkdir()
    log.write_text("last session\n", encoding="utf-8")
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    with console_log(log, previous=previous) as path:
        print("this session")
        sys.stderr.write("its warning\n")

    assert path == log
    assert (sys.stdout, sys.stderr) == (None, None)
    assert log.read_text(encoding="utf-8") == "this session\nits warning\n"
    assert previous.read_text(encoding="utf-8") == "last session\n"


def test_a_start_in_a_console_keeps_writing_to_it(tmp_path: Path) -> None:
    streams = (sys.stdout, sys.stderr)
    log = tmp_path / "logs" / "app-key.log"

    with console_log(log, previous=tmp_path / "logs" / "app-key.previous.log") as path:
        assert path is None
        assert (sys.stdout, sys.stderr) == streams

    assert not log.parent.exists()
