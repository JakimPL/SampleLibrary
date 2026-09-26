from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def console_log(log: Path, *, previous: Path) -> Iterator[Path | None]:
    """Send the application's output to ``log`` while it runs without a console, and yield that file.

    The packaged application starts on Windows through pythonw, which leaves stdout and stderr unset.
    Each such start keeps the log of the one before it at ``previous``, so the log of a session that
    ended badly survives the next start. The log closes as the block ends, which is before the
    application lets its place go, so the start taking over next can move it aside.
    """
    if sys.stdout is not None and sys.stderr is not None:
        yield None
        return
    console_streams = (sys.stdout, sys.stderr)
    log.parent.mkdir(parents=True, exist_ok=True)
    if log.is_file():
        log.replace(previous)
    with log.open("w", encoding="utf-8", errors="backslashreplace", buffering=1) as stream:
        sys.stdout = stream
        sys.stderr = stream
        try:
            yield log
        finally:
            sys.stdout, sys.stderr = console_streams
