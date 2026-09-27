from __future__ import annotations

import shutil
from pathlib import Path
from typing import Final

from samplecore.storage.atomic import PARTIAL_SUFFIX, synchronize_directory, synchronize_file

RETIRED_SUFFIX: Final[str] = ".retired"


def partial_path(artifact: Path) -> Path:
    """Where a build of `artifact` keeps what it has finished until it publishes: a hidden directory beside it.

    A build stopped partway leaves it in place, so the next build of the same artifact continues
    from it, and the pipeline knows every artifact's partial by this one rule.
    """
    return _sibling(artifact, suffix=PARTIAL_SUFFIX)


def fresh_staging(artifact: Path) -> Path:
    """An empty partial beside `artifact` to build in, cleared of whatever a stopped build left there."""
    staging = partial_path(artifact)
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    return staging


def publish_staged(staging: Path, directory: Path, *, file_names: tuple[str, ...]) -> None:
    """Flush a finished build to disk and move it under its name, retiring whichever build held the name before.

    A build stopped partway leaves the previous build under that name as it was, a machine stopping
    right after the move keeps the new one whole, and a reader already holding the previous build
    keeps the files it mapped. `file_names` are the files the build consists of, which are flushed
    before the move.
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


def _sibling(path: Path, *, suffix: str) -> Path:
    return path.with_name(f".{path.name}{suffix}")
