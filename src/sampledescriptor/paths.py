from __future__ import annotations

from pathlib import Path
from typing import Final

PACKAGE_DIRECTORY: Final[Path] = Path(__file__).resolve().parent
PRETRAINED_RELEASE_PATH: Final[Path] = PACKAGE_DIRECTORY / "pretrained.toml"
