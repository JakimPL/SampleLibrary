from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

from platformdirs import user_log_path

from samplecore.config import APPLICATION_NAME

LOG_NAME: Final[str] = "app.log"
PREVIOUS_LOG_NAME: Final[str] = "app.previous.log"


def log_without_console() -> Path | None:
    """Send the application's output to its log file when it runs without a console, and return that file.

    The packaged application starts on Windows through pythonw, which leaves stdout and stderr unset.
    Each such start keeps the log of the one before it beside its own, so the log of a session that
    ended badly survives the next start.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return None
    directory = user_log_path(APPLICATION_NAME, appauthor=False)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / LOG_NAME
    if path.is_file():
        path.replace(directory / PREVIOUS_LOG_NAME)
    # pylint: disable-next=consider-using-with
    stream = path.open("w", encoding="utf-8", errors="backslashreplace", buffering=1)
    sys.stdout = stream
    sys.stderr = stream
    return path
