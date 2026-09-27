from __future__ import annotations

import os
from collections.abc import Callable
from typing import Final

import psutil
from pydantic import BaseModel, ConfigDict

START_TIME_TOLERANCE_SECONDS: Final[float] = 1.0


class ProcessIdentity(BaseModel):
    """One process, told apart from a later one the system gives the same id by the moment it started.

    A record one version of the application writes is read by the next, so the model reads past
    fields it does not know.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    pid: int
    started_at: float


def current_process() -> ProcessIdentity:
    process = psutil.Process(os.getpid())
    return ProcessIdentity(pid=process.pid, started_at=process.create_time())


def is_running(identity: ProcessIdentity) -> bool:
    """Whether the process ``identity`` names is still running, and is that process rather than a later one."""
    try:
        process = psutil.Process(identity.pid)
        return _started_as(process, identity) and process.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def end_process_tree(identity: ProcessIdentity, *, grace_seconds: float) -> None:
    """End the process ``identity`` names and every process it started: asked first, forced once ``grace_seconds`` pass.

    The children are gathered before the process is touched, since a child whose parent has
    ended belongs to the system from then on and reads as nobody's.
    """
    try:
        process = psutil.Process(identity.pid)
        if not _started_as(process, identity):
            return
        tree = [process, *process.children(recursive=True)]
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return
    _signal_each(tree, psutil.Process.terminate)
    _, remaining = psutil.wait_procs(tree, timeout=grace_seconds)
    _signal_each(remaining, psutil.Process.kill)
    psutil.wait_procs(remaining, timeout=grace_seconds)


def _started_as(process: psutil.Process, identity: ProcessIdentity) -> bool:
    return abs(process.create_time() - identity.started_at) < START_TIME_TOLERANCE_SECONDS


def _signal_each(processes: list[psutil.Process], signal: Callable[[psutil.Process], None]) -> None:
    for process in processes:
        try:
            signal(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
