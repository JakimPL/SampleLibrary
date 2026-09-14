from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from samplelibrary.environment import MEMORY_SCOPE_ENVIRONMENT_VARIABLE
from samplelibrary.limits import systemd
from samplelibrary.limits.bare import BareScope
from samplelibrary.limits.ceiling import MemoryCeiling
from samplelibrary.limits.probe import memory_scope
from samplelibrary.limits.scope import MemoryScopeUnavailable
from samplelibrary.limits.systemd import SystemdScope

SCOPE_NAME = "samplelibrary-test-step"
CEILING = MemoryCeiling.parse("2G")


def test_a_system_holding_no_ceiling_runs_on_without_one() -> None:
    BareScope().enter(SCOPE_NAME, MemoryCeiling.parse("none"), [])


def test_a_ceiling_a_system_cannot_hold_is_refused() -> None:
    with pytest.raises(MemoryScopeUnavailable, match="ceiling of none"):
        BareScope().enter(SCOPE_NAME, CEILING, ["extract"])


def _recorded_execution(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    executed: list[list[str]] = []
    monkeypatch.setattr(systemd.subprocess, "run", lambda *arguments, **keywords: _completed())
    monkeypatch.setattr(systemd.os, "execvp", lambda program, command: executed.append(list(command)))
    return executed


def _completed() -> Any:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")


def test_a_capped_command_starts_again_inside_a_scope_of_its_own_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(MEMORY_SCOPE_ENVIRONMENT_VARIABLE, raising=False)
    executed = _recorded_execution(monkeypatch)

    SystemdScope().enter(
        SCOPE_NAME, CEILING, [sys.executable, "-m", "samplelibrary", "--memory-cap", "2G", "extract", "--workers", "2"]
    )

    (command,) = executed
    assert command[:5] == ["systemd-run", "--user", "--scope", "--collect", "--quiet"]
    assert f"--unit={SCOPE_NAME}" in command
    assert f"MemoryMax={CEILING.byte_count}" in command
    assert "MemorySwapMax=0" in command
    assert command[command.index("--") + 1 :] == [
        sys.executable,
        "-m",
        "samplelibrary",
        "--memory-cap",
        "2G",
        "extract",
        "--workers",
        "2",
    ]


def _cgroup_holding(directory: Path, *, memory_max: str, swap_max: str) -> Path:
    (directory / "memory.max").write_text(memory_max, encoding="utf-8")
    (directory / "memory.swap.max").write_text(swap_max, encoding="utf-8")
    return directory


def test_a_process_already_in_its_scope_reads_the_ceiling_the_kernel_holds_it_to(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(MEMORY_SCOPE_ENVIRONMENT_VARIABLE, SCOPE_NAME)
    monkeypatch.setattr(
        systemd, "_own_cgroup", lambda: _cgroup_holding(tmp_path, memory_max=str(CEILING.byte_count), swap_max="0")
    )
    executed = _recorded_execution(monkeypatch)

    SystemdScope().enter(SCOPE_NAME, CEILING, [])

    assert executed == []


@pytest.mark.parametrize(
    ("memory_max", "swap_max"),
    [("max", "0"), (str(CEILING.byte_count), "max"), ("1024", "0")],
    ids=("no memory ceiling", "swap left open", "another ceiling"),
)
def test_a_scope_that_does_not_hold_the_ceiling_asked_for_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, memory_max: str, swap_max: str
) -> None:
    monkeypatch.setenv(MEMORY_SCOPE_ENVIRONMENT_VARIABLE, SCOPE_NAME)
    monkeypatch.setattr(
        systemd, "_own_cgroup", lambda: _cgroup_holding(tmp_path, memory_max=memory_max, swap_max=swap_max)
    )

    with pytest.raises(MemoryScopeUnavailable, match="control group"):
        SystemdScope().enter(SCOPE_NAME, CEILING, [])


def test_a_session_with_no_user_manager_refuses_the_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(MEMORY_SCOPE_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.setattr(
        systemd.subprocess,
        "run",
        lambda *arguments, **keywords: subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="Failed to connect to bus"
        ),
    )

    with pytest.raises(MemoryScopeUnavailable, match="could not open a scope"):
        SystemdScope().enter(SCOPE_NAME, CEILING, [])


@pytest.mark.skipif(sys.platform == "win32", reason="the systemd scope is the Linux way of holding a ceiling")
def test_linux_holds_a_ceiling_through_systemd_where_it_is_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda program: "/usr/bin/systemd-run")
    assert isinstance(memory_scope(), SystemdScope)

    monkeypatch.setattr(shutil, "which", lambda program: None)
    assert isinstance(memory_scope(), BareScope)
