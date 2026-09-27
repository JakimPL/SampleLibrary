from __future__ import annotations

from pathlib import Path
from typing import Final

from platformdirs import user_log_path, user_state_path

from samplecore.paths import APPLICATION_NAME

PACKAGE_DIRECTORY: Final[Path] = Path(__file__).resolve().parent
PACKAGED_FRONTEND_DIRECTORY: Final[Path] = PACKAGE_DIRECTORY / "app" / "frontend"
INSTANCES_DIRECTORY_NAME: Final[str] = "instances"
INSTANCE_LOCK_NAME: Final[str] = "instance.lock"
INSTANCE_RECORD_NAME: Final[str] = "instance.json"
LIBRARY_LOCKS_DIRECTORY_NAME: Final[str] = "libraries"
LIBRARY_LOCK_SUFFIX: Final[str] = ".lock"
PUBLICATION_DIRECTORY_NAME: Final[str] = "publication"


def application_log_path(key: str) -> Path:
    """The log a windowless application running under the config ``key`` names writes, in the user's log folder."""
    return user_log_path(APPLICATION_NAME, appauthor=False) / f"app-{key}.log"


def previous_application_log_path(key: str) -> Path:
    """The log the start before the current one under the same config wrote."""
    return user_log_path(APPLICATION_NAME, appauthor=False) / f"app-{key}.previous.log"


def instances_directory() -> Path:
    """The folder holding one place for each config the application runs under, in the user's state folder."""
    return user_state_path(APPLICATION_NAME, appauthor=False) / INSTANCES_DIRECTORY_NAME


def publication_directory(library_root: Path) -> Path:
    """The folder `sampleripper publish` builds a site's audio store in, beside the library's own."""
    return library_root / PUBLICATION_DIRECTORY_NAME
