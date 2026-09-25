from __future__ import annotations

import sys
from pathlib import Path

from samplelibrary.paths import APPLICATION_LOG_NAME, PREVIOUS_APPLICATION_LOG_NAME, application_log_directory


def log_without_console() -> Path | None:
    """Send the application's output to its log file when it runs without a console, and return that file.

    The packaged application starts on Windows through pythonw, which leaves stdout and stderr unset.
    Each such start keeps the log of the one before it beside its own, so the log of a session that
    ended badly survives the next start.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return None
    directory = application_log_directory()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / APPLICATION_LOG_NAME
    if path.is_file():
        path.replace(directory / PREVIOUS_APPLICATION_LOG_NAME)
    # pylint: disable-next=consider-using-with
    stream = path.open("w", encoding="utf-8", errors="backslashreplace", buffering=1)
    sys.stdout = stream
    sys.stderr = stream
    return path
