from __future__ import annotations

from pathlib import Path
from typing import Final

PACKAGE_DIRECTORY: Final[Path] = Path(__file__).resolve().parent
SELECTIONS_DIRECTORY: Final[Path] = PACKAGE_DIRECTORY / "routes" / "selections"
DEFAULT_SELECTION_PATH: Final[Path] = SELECTIONS_DIRECTORY / "morph.yaml"
DEFAULT_FILTER_SELECTION_PATH: Final[Path] = SELECTIONS_DIRECTORY / "morph-filter.yaml"
