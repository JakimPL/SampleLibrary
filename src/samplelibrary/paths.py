from __future__ import annotations

from pathlib import Path
from typing import Final

from platformdirs import user_log_path

from samplecore.paths import APPLICATION_NAME

PACKAGE_DIRECTORY: Final[Path] = Path(__file__).resolve().parent
PACKAGED_FRONTEND_DIRECTORY: Final[Path] = PACKAGE_DIRECTORY / "app" / "frontend"
APPLICATION_LOG_NAME: Final[str] = "app.log"
PREVIOUS_APPLICATION_LOG_NAME: Final[str] = "app.previous.log"


def application_log_directory() -> Path:
    """The folder a windowless application writes its log into, the system's own for the user's logs."""
    return user_log_path(APPLICATION_NAME, appauthor=False)
