from __future__ import annotations

from pathlib import Path
from typing import Final

MODELS_DIRECTORY_NAME: Final[str] = "models"
DESCRIPTORS_DIRECTORY_NAME: Final[str] = "descriptors"
DESCRIPTOR_SUFFIX: Final[str] = ".pt"
DEFAULT_DESCRIPTOR_NAME: Final[str] = "descriptor"


def descriptor_path(library_root: Path, *, name: str) -> Path:
    """Where a fitted descriptor is written, under the library root beside the other models."""
    return library_root / MODELS_DIRECTORY_NAME / DESCRIPTORS_DIRECTORY_NAME / f"{name}{DESCRIPTOR_SUFFIX}"
