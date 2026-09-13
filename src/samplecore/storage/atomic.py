from __future__ import annotations

import os
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
    their files does.
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
