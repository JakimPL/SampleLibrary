from __future__ import annotations

from pathlib import Path
from typing import Final

from platformdirs import user_log_path, user_state_path

from samplecore.paths import APPLICATION_NAME

PACKAGE_DIRECTORY: Final[Path] = Path(__file__).resolve().parent
PACKAGED_FRONTEND_DIRECTORY: Final[Path] = PACKAGE_DIRECTORY / "app" / "frontend"
APPLICATION_LOG_NAME: Final[str] = "app.log"
PREVIOUS_APPLICATION_LOG_NAME: Final[str] = "app.previous.log"
INSTANCES_DIRECTORY_NAME: Final[str] = "instances"
INSTANCE_LOCK_NAME: Final[str] = "instance.lock"
INSTANCE_RECORD_NAME: Final[str] = "instance.json"


def application_log_directory() -> Path:
    """The folder a windowless application writes its log into, the system's own for the user's logs."""
    return user_log_path(APPLICATION_NAME, appauthor=False)


def instances_directory() -> Path:
    """The folder holding one place for each config the application runs under, in the user's state folder."""
    return user_state_path(APPLICATION_NAME, appauthor=False) / INSTANCES_DIRECTORY_NAME
