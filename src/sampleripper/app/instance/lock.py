from __future__ import annotations

from pathlib import Path
from types import TracebackType

from filelock import FileLock, Timeout


class LockUnavailableError(Exception):
    """Raised when the folder meant to hold a lock sits on a filesystem that cannot hold one."""


class HeldLock:
    """A lock this process holds until it releases it or ends, when the system lets it go.

    The lock stays with this process alone: the application starts every other program by fork
    and exec, and the file descriptor under the lock closes at exec, so no child keeps it.
    """

    def __init__(self, lock: FileLock) -> None:
        self._lock = lock

    def release(self) -> None:
        self._lock.release()

    def __enter__(self) -> HeldLock:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()


def try_lock(path: Path) -> HeldLock | None:
    """The lock at ``path``, or None while another process holds it.

    The system's own file lock backs it, which ends with the process holding it however that
    process ends, so a lock that stays held marks a process that is still running.

    Raises:
        LockUnavailableError: the filesystem at ``path`` cannot hold the lock.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(path, thread_local=False, fallback_to_soft=False, preserve_lock_file=True)
    try:
        lock.acquire(timeout=0)
    except Timeout:
        return None
    except OSError as error:
        raise LockUnavailableError(f"{path.parent} can't hold SampleRipper's lock: {error}") from error
    return HeldLock(lock)
