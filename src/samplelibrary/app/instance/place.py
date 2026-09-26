from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from samplelibrary.paths import INSTANCE_LOCK_NAME, INSTANCE_RECORD_NAME, instances_directory

KEY_LENGTH: Final[int] = 16


@dataclass(frozen=True)
class InstancePlace:
    """Where the application running under one config keeps the lock it holds and the record of where it listens.

    Each config gets a place of its own, so the installed application, a source checkout and a smoke
    test each run beside the others, while two starts under one config meet at one lock.
    """

    key: str
    directory: Path

    @property
    def lock(self) -> Path:
        return self.directory / INSTANCE_LOCK_NAME

    @property
    def record(self) -> Path:
        return self.directory / INSTANCE_RECORD_NAME


def config_key(config_path: Path) -> str:
    """A short name for a config file, the same for every spelling of its path.

    Windows compares paths regardless of case, so the key reads the path the same way there.
    """
    resolved = str(config_path.resolve())
    if sys.platform == "win32":
        resolved = resolved.casefold()
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:KEY_LENGTH]


def instance_place(config_path: Path) -> InstancePlace:
    key = config_key(config_path)
    return InstancePlace(key=key, directory=instances_directory() / key)
