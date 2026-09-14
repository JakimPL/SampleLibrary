from __future__ import annotations

from pathlib import Path
from typing import Final

MODELS_DIRECTORY_NAME: Final[str] = "models"
CODECS_DIRECTORY_NAME: Final[str] = "codecs"
DESCRIPTORS_DIRECTORY_NAME: Final[str] = "descriptors"
CODEC_SUFFIX: Final[str] = ".pt"
DESCRIPTOR_SUFFIX: Final[str] = ".pt"
RESTORER_SUFFIX: Final[str] = ".pt"
CONDITIONED_CODEC_NAME: Final[str] = "conditioned"
DEFAULT_CODEC_NAME: Final[str] = "conditioned"
DEFAULT_DESCRIPTOR_NAME: Final[str] = "descriptor"
DEFAULT_RESTORER_NAME: Final[str] = "restorer"


def codec_path(library_root: Path, *, name: str) -> Path:
    """Where a fitted conditioned codec is written, under the library root beside the other models."""
    return library_root / MODELS_DIRECTORY_NAME / CODECS_DIRECTORY_NAME / f"{name}{CODEC_SUFFIX}"


def descriptor_path(library_root: Path, *, name: str) -> Path:
    """Where a fitted descriptor is written, under the library root beside the other models."""
    return library_root / MODELS_DIRECTORY_NAME / DESCRIPTORS_DIRECTORY_NAME / f"{name}{DESCRIPTOR_SUFFIX}"


def restorer_path(library_root: Path, *, name: str) -> Path:
    """Where a fitted restorer is written, under the configured library root rather than the repo."""
    return library_root / MODELS_DIRECTORY_NAME / f"{name}{RESTORER_SUFFIX}"
