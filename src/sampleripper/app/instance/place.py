from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from sampleripper.paths import (
    INSTANCE_LOCK_NAME,
    INSTANCE_RECORD_NAME,
    LIBRARY_LOCK_SUFFIX,
    LIBRARY_LOCKS_DIRECTORY_NAME,
    application_log_path,
    instances_directory,
    previous_application_log_path,
)

KEY_LENGTH: Final[int] = 16


@dataclass(frozen=True)
class InstancePlace:
    """Where the application running under one config keeps its lock, the record of where it listens, and its log.

    Each config gets a place of its own, so the installed application, a source checkout and a smoke
    test each run beside the others, while two starts under one config meet at one lock.
    """

    key: str
    directory: Path
    log: Path
    previous_log: Path

    @property
    def lock(self) -> Path:
        return self.directory / INSTANCE_LOCK_NAME

    @property
    def record(self) -> Path:
        return self.directory / INSTANCE_RECORD_NAME


def path_key(path: Path) -> str:
    """A short name for a file or folder, the same for every spelling of its path.

    Windows compares paths regardless of case, so the key reads the path the same way there.
    """
    resolved = str(path.resolve())
    if sys.platform == "win32":
        resolved = resolved.casefold()
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:KEY_LENGTH]


def instance_place(config_path: Path) -> InstancePlace:
    key = path_key(config_path)
    return InstancePlace(
        key=key,
        directory=instances_directory() / key,
        log=application_log_path(key),
        previous_log=previous_application_log_path(key),
    )


def library_lock_path(library_root: Path) -> Path:
    """The lock an application holds while a library is open under it, whichever config names the library."""
    return instances_directory() / LIBRARY_LOCKS_DIRECTORY_NAME / f"{path_key(library_root)}{LIBRARY_LOCK_SUFFIX}"
