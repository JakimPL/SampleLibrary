from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import BaseModel, Field

from samplecore.hashing import file_sha256
from samplecore.models.base import FROZEN
from sampledescriptor.geometry import Anchor

PRETRAINED_DIRECTORY: Final[Path] = Path(__file__).resolve().parent / "pretrained"
PRETRAINED_MODEL_NAME: Final[str] = "descriptor.pt"
PRETRAINED_MANIFEST_NAME: Final[str] = "descriptor.json"


class PretrainedDescriptorMissingError(Exception):
    """Raised when a library asks for the pretrained descriptor and this installation carries none."""


class PretrainedManifest(BaseModel):
    """What the grid cache must be read under for the bundled descriptor to describe it.

    The bundling script writes it from the descriptor's own description, so the pipeline learns the
    axis without loading the network.
    """

    model_config = FROZEN

    canonicalizer: str
    anchor: Anchor
    bands_per_semitone: int = Field(ge=1)


@dataclass(frozen=True)
class PretrainedDescriptor:
    """The descriptor shipped with the application, and the grid it reads."""

    model: Path
    manifest: PretrainedManifest

    @property
    def content(self) -> str:
        """The digest of the model's bytes, which names every output built from it."""
        return file_sha256(self.model)


def pretrained_descriptor() -> PretrainedDescriptor:
    """The descriptor bundled into this installation.

    Raises:
        PretrainedDescriptorMissingError: the installation carries no bundled descriptor.
    """
    return read_pretrained(PRETRAINED_DIRECTORY)


def read_pretrained(directory: Path) -> PretrainedDescriptor:
    """The descriptor a bundle directory holds.

    Raises:
        PretrainedDescriptorMissingError: the directory holds no complete bundle.
    """
    model = directory / PRETRAINED_MODEL_NAME
    manifest = directory / PRETRAINED_MANIFEST_NAME
    if not model.is_file() or not manifest.is_file():
        raise PretrainedDescriptorMissingError(
            "No pretrained descriptor is installed. Run `just bundle-descriptor` after training one, "
            'or set descriptor_source = "trained" in the [pipeline] table of the config.'
        )
    return PretrainedDescriptor(
        model=model, manifest=PretrainedManifest.model_validate_json(manifest.read_text(encoding="utf-8"))
    )
