from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Final

from samplelibrary.environment import MEMORY_SCOPE_ENVIRONMENT_VARIABLE
from samplelibrary.limits.ceiling import MemoryCeiling
from samplelibrary.limits.scope import MemoryScopeUnavailable

SYSTEMD_RUN: Final[str] = "systemd-run"
SYSTEMCTL: Final[str] = "systemctl"
SCOPE_SUFFIX: Final[str] = ".scope"
CGROUP_ROOT: Final[Path] = Path("/sys/fs/cgroup")
MEMORY_MAX_FILE: Final[str] = "memory.max"
MEMORY_SWAP_MAX_FILE: Final[str] = "memory.swap.max"
MEMORY_PEAK_FILE: Final[str] = "memory.peak"
MEMORY_EVENTS_FILE: Final[str] = "memory.events"
PROBE_TIMEOUT_SECONDS: Final[int] = 30

_logger = logging.getLogger(__name__)


class SystemdScope:
    """A memory ceiling held by a systemd scope of the user's own session, which the kernel enforces.

    The process starts itself again inside the scope, so the command runs as one process under the
    ceiling rather than beside a wrapper, and everything it starts joins the same control group.
    Swap is closed off with the ceiling, so a run that outgrows it is stopped rather than dragging
    the machine into swapping.
    """

    def enter(self, name: str, ceiling: MemoryCeiling, restart: list[str]) -> None:
        """Start this process again inside a scope of this name, and verify the kernel holds it there.

        Raises:
            MemoryScopeUnavailable: this session runs no user manager that can open a scope, or the
                scope it opened holds no ceiling.
        """
        if ceiling.byte_count is None:
            return
        if os.environ.get(MEMORY_SCOPE_ENVIRONMENT_VARIABLE) == name:
            _require_enforcement(ceiling)
            return

        _require_a_user_manager()
        subprocess.run([SYSTEMCTL, "--user", "reset-failed", f"{name}{SCOPE_SUFFIX}"], check=False, capture_output=True)
        os.environ[MEMORY_SCOPE_ENVIRONMENT_VARIABLE] = name
        command = [
            SYSTEMD_RUN,
            "--user",
            "--scope",
            "--collect",
            "--quiet",
            f"--unit={name}",
            "-p",
            f"MemoryMax={ceiling.byte_count}",
            "-p",
            "MemorySwapMax=0",
            "--",
            *restart,
        ]
        os.execvp(command[0], command)

    def is_running(self, name: str) -> bool:
        """Whether the scope of this name is still active, which is what an orphaned step leaves behind."""
        finished = subprocess.run(
            [SYSTEMCTL, "--user", "is-active", f"{name}{SCOPE_SUFFIX}"], check=False, capture_output=True, text=True
        )
        return finished.stdout.strip() == "active"

    def terminate(self, name: str) -> None:
        """Kill every process in the scope of this name, which is how a whole step's tree goes at once."""
        subprocess.run(
            [SYSTEMCTL, "--user", "kill", "--signal=KILL", f"{name}{SCOPE_SUFFIX}"], check=False, capture_output=True
        )

    def peak_bytes(self) -> int | None:
        """The most memory this control group ever held at once, as the kernel recorded it."""
        return _read_integer(_own_cgroup() / MEMORY_PEAK_FILE)

    def reached_the_ceiling(self) -> bool:
        """Whether the kernel stopped anything in this control group for outgrowing the ceiling."""
        events = _own_cgroup() / MEMORY_EVENTS_FILE
        try:
            lines = events.read_text(encoding="utf-8").splitlines()
        except OSError:
            return False
        return any(line.startswith("oom_kill ") and line.split()[1] != "0" for line in lines)


def _require_a_user_manager() -> None:
    """Make sure this session has a user manager that opens scopes, before a command is handed to it.

    Raises:
        MemoryScopeUnavailable: no user manager answers, so no ceiling can be set here.
    """
    probe = subprocess.run(
        [SYSTEMD_RUN, "--user", "--scope", "--quiet", "--collect", "--", "true"],
        check=False,
        capture_output=True,
        text=True,
        timeout=PROBE_TIMEOUT_SECONDS,
    )
    if probe.returncode != 0:
        raise MemoryScopeUnavailable(
            f"{SYSTEMD_RUN} could not open a scope in this session ({probe.stderr.strip() or probe.returncode})"
        )


def _require_enforcement(ceiling: MemoryCeiling) -> None:
    """Read back the ceiling the kernel holds this process to.

    Raises:
        MemoryScopeUnavailable: the control group holds another ceiling than the one asked for, or none.
    """
    cgroup = _own_cgroup()
    held = _read_integer(cgroup / MEMORY_MAX_FILE)
    swap = _read_integer(cgroup / MEMORY_SWAP_MAX_FILE)
    if held != ceiling.byte_count or swap != 0:
        raise MemoryScopeUnavailable(
            f"the control group under {cgroup} holds {held} bytes of memory and {swap} of swap, "
            f"where {ceiling.byte_count} and 0 were asked for"
        )


def _own_cgroup() -> Path:
    """The directory of this process's own control group."""
    line = Path("/proc/self/cgroup").read_text(encoding="utf-8").strip().splitlines()[-1]
    return CGROUP_ROOT / line.rsplit(":", maxsplit=1)[-1].lstrip("/")


def _read_integer(path: Path) -> int | None:
    """The number a control-group file holds, with ``max`` reading as no limit at all."""
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return None if value == "max" else int(value)
