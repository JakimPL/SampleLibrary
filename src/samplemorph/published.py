from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Final

from pydantic import BaseModel

from samplecore.hashing import file_sha256
from samplecore.models.base import FROZEN
from samplecore.models.sample_file import FileFingerprint
from samplemorph.model_paths import DEFAULT_RESTORER_NAME, MODELS_DIRECTORY_NAME, restorer_path
from samplemorph.model_store import DEFAULT_MODEL_NAME, model_path

PUBLISHED_RECORD_NAME: Final[str] = "published.json"


class PublishedModel(BaseModel):
    """One model the renderer loads by its default name: the stored model it was copied from, and what it holds."""

    model_config = FROZEN

    source: str
    content: str
    fingerprint: FileFingerprint


class PublishedModels(BaseModel):
    """The codec and the restorer the morph service loads by default, recorded once both stand in place."""

    model_config = FROZEN

    codec: PublishedModel
    restorer: PublishedModel
    published_at: datetime


def published_record_path(library_root: Path) -> Path:
    """Where the record of the published models sits, beside the models themselves."""
    return library_root / MODELS_DIRECTORY_NAME / PUBLISHED_RECORD_NAME


def published_codec_path(library_root: Path) -> Path:
    """The codec the renderer loads when a request names none."""
    return model_path(library_root, name=DEFAULT_MODEL_NAME)


def published_restorer_path(library_root: Path) -> Path:
    """The restorer the renderer loads when a request names none."""
    return restorer_path(library_root, name=DEFAULT_RESTORER_NAME)


def read_published(library_root: Path) -> PublishedModels | None:
    """The record of the models last published, or nothing where none was, or the record cannot be read."""
    path = published_record_path(library_root)
    if not path.is_file():
        return None
    try:
        return PublishedModels.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        return None


def holds_published(path: Path, published: PublishedModel) -> bool:
    """Whether a published model's file holds what the record says, read again only where its file moved."""
    if not path.is_file():
        return False
    if FileFingerprint.of(path.stat()) == published.fingerprint:
        return True
    return file_sha256(path) == published.content
