from __future__ import annotations

import shutil
from pathlib import Path
from typing import Final

from build_app import APP_NAME

PROGRAM_MODE: Final[int] = 0o755


def release_name(version: str, platform: str) -> str:
    """The name a release file carries before its extension, such as SampleRipper-0.1.0-linux-x64."""
    return f"{APP_NAME}-{version}-{platform}"


def copy_program(source: Path, target: Path) -> None:
    """Copy a program or a launcher script into a package, runnable by everyone."""
    shutil.copy2(source, target)
    target.chmod(PROGRAM_MODE)
