from __future__ import annotations

import shutil
from pathlib import Path
from typing import Final

from samplecore.storage.atomic import synchronize_directory, synchronize_file

CACHE_DIRECTORY_NAME: Final[str] = "cache"
STAGING_SUFFIX: Final[str] = ".partial"
RETIRED_SUFFIX: Final[str] = ".retired"


def fresh_staging(directory: Path) -> Path:
    """An empty directory beside `directory` to build a cache in, cleared of whatever a stopped build left there."""
    staging = _sibling(directory, suffix=STAGING_SUFFIX)
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    return staging


def publish_staged(staging: Path, directory: Path, *, file_names: tuple[str, ...]) -> None:
    """Flush a finished cache to disk and move it under its name, retiring whichever cache held the name before.

    A build stopped partway leaves the previous cache under that name as it was, a machine stopping
    right after the move keeps the new one whole, and a trainer already reading the previous cache
    keeps the files it mapped.
    """
    for name in file_names:
        synchronize_file(staging / name)
    synchronize_directory(staging)
    retired = _sibling(directory, suffix=RETIRED_SUFFIX)
    shutil.rmtree(retired, ignore_errors=True)
    if directory.exists():
        directory.replace(retired)
    staging.replace(directory)
    synchronize_directory(directory.parent)
    shutil.rmtree(retired, ignore_errors=True)


def _sibling(directory: Path, *, suffix: str) -> Path:
    return directory.with_name(f".{directory.name}{suffix}")
