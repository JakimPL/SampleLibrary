from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import IO, Final

PARTIAL_SUFFIX: Final[str] = ".partial"
_PLAIN_FILE_PERMISSIONS: Final[int] = 0o666


def _process_umask() -> int:
    """The permission bits this process withholds from the files it creates, read and put back as they were."""
    withheld = os.umask(0)
    os.umask(withheld)
    return withheld


PLAIN_FILE_MODE: Final[int] = _PLAIN_FILE_PERMISSIONS & ~_process_umask()


def write_atomically(path: Path, write: Callable[[IO[bytes]], None]) -> None:
    """Put a file in place whole: written beside its destination, flushed to disk, then moved over it.

    A reader of ``path`` finds either what was there before or the complete new content, and a
    process stopped partway leaves only a ``.partial`` file beside it, removed on the way out when
    the writer raises. Staging in the destination's own directory keeps the move on one filesystem,
    which is what makes it a single step. The file ends with the permissions a plain ``open`` gives
    under this process's umask, so a library one user writes reads for another user the way any of
    their files does. The directory is flushed after the move, so the new name survives a machine
    that stops right after this returns.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, suffix=PARTIAL_SUFFIX, delete_on_close=False) as partial:
        write(partial)
        partial.flush()
        os.fsync(partial.fileno())
        partial.close()
        staged = Path(partial.name)
        staged.chmod(PLAIN_FILE_MODE)
        staged.replace(path)
    synchronize_directory(path.parent)


def write_bytes_atomically(path: Path, content: bytes) -> None:
    """Put ``content`` in place at ``path`` whole, the way `write_atomically` puts any file."""

    def write(file: IO[bytes]) -> None:
        file.write(content)

    write_atomically(path, write)


def synchronize_file(path: Path) -> None:
    """Flush a file another writer produced to disk, so its content survives a crash along with its name.

    For files built in place by a library of their own, such as a memory map, before they move into
    a name that readers trust.
    """
    with path.open("r+b") as file:
        os.fsync(file.fileno())


def synchronize_directory(directory: Path) -> None:
    """Flush a directory's entries to disk, so a file created, renamed or removed in it stays that way after a crash.

    Windows commits a rename through its file system's own journal and opens no handle on a
    directory for this, so the flush applies to POSIX systems.
    """
    if sys.platform == "win32":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
