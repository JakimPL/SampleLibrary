from __future__ import annotations

from pathlib import Path
from typing import Final

CACHE_DIRECTORY_NAME: Final[str] = "cache"
SAMPLE_LAYOUT_DIRECTORY_NAME: Final[str] = "cloud"
MODULE_LAYOUT_DIRECTORY_NAME: Final[str] = "module-cloud"
LAYOUT_RECORD_FILE_NAME: Final[str] = "layout.json"


def sample_layout_directory(library_root: Path) -> Path:
    """Where the sample cloud keeps the stages of the layout it is fitting, beside the library's other caches."""
    return library_root / CACHE_DIRECTORY_NAME / SAMPLE_LAYOUT_DIRECTORY_NAME


def module_layout_directory(library_root: Path) -> Path:
    """Where the module cloud keeps the stages of its layout and the record of the last layout it finished."""
    return library_root / CACHE_DIRECTORY_NAME / MODULE_LAYOUT_DIRECTORY_NAME
