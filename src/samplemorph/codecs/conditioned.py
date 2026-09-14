from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import torch
from numpy.typing import NDArray
from pydantic import BaseModel
from torch import Tensor

from samplecore.hashing import file_sha256
from samplecore.models.base import FROZEN
from samplecore.storage.atomic import write_atomically
from samplemorph.codecs.conditioned_model import ConditionedCodecModel, ConditionedCodecShape
from samplemorph.descriptors.learned import LearnedDescriptor, descriptor_path, load_descriptor
from samplemorph.geometry import Geometry
from samplemorph.images import SampleLatent, SoundImage

CONDITIONED_CODEC_NAME: Final[str] = "conditioned"
CODECS_DIRECTORY_NAME: Final[str] = "codecs"
CODEC_SUFFIX: Final[str] = ".pt"
DEFAULT_CODEC_NAME: Final[str] = "conditioned"


class ConditionedCodecDescription(BaseModel):
    """What a fitted conditioned codec is, recorded beside its weights so a file explains itself."""

    model_config = FROZEN

    canonicalizer: str
    geometry: Geometry
    shape: ConditionedCodecShape
    descriptor: str
    descriptor_sha256: str
    epochs: int
    trained_sample_count: int
    random_seed: int
    best_validation_loss: float


@dataclass(frozen=True)
class ConditionedCodec:
    """Encodes a grid as its descriptor beside a residual, and decodes from the two together.

    The latent a morph travels through is the descriptor followed by the residual, so a straight
    line between two latents moves the sound's identity through the space the harness judges and
    its particulars through a space with a prior. Decoding brings the descriptor part back to unit
    length, since a point between two unit vectors falls inside the sphere the decoder was taught on.
    """

    model: ConditionedCodecModel
    description: ConditionedCodecDescription
    descriptor: LearnedDescriptor
    geometry: Geometry
    device: torch.device

    @property
    def latent_size(self) -> int:
        return self.model.shape.descriptor_size + self.model.shape.residual_length

    def encode(self, image: SoundImage) -> SampleLatent:
        """The descriptor followed by the residual's mean, flattened whatever its layout."""
        described = self.descriptor.describe(image)
        grid = torch.from_numpy(image.grid.astype(np.float32))[None].to(self.device)
        with torch.no_grad():
            mean, _ = self.model.encode(grid, torch.from_numpy(described.astype(np.float32))[None].to(self.device))
        values = np.concatenate([described, mean[0].cpu().numpy().astype(np.float64).reshape(-1)])
        return SampleLatent(values=values, conditioners=image.conditioners, geometry=image.geometry)

    def decode(self, latent: SampleLatent) -> SoundImage:
        described, residual = self.split(torch.from_numpy(latent.values.astype(np.float32))[None].to(self.device))
        with torch.no_grad():
            grid = self.model.decode(
                residual.view(-1, *self.model.shape.residual_shape), torch.nn.functional.normalize(described, dim=-1)
            )
        restored: NDArray[np.float64] = np.clip(grid[0].cpu().numpy().astype(np.float64), 0.0, 1.0)
        return SoundImage(grid=restored, conditioners=latent.conditioners, geometry=latent.geometry)

    def split(self, values: Tensor) -> tuple[Tensor, Tensor]:
        """A latent's two halves: the descriptor it was encoded beside, and the residual flattened."""
        return values[:, : self.model.shape.descriptor_size], values[:, self.model.shape.descriptor_size :]


def codec_path(library_root: Path, *, name: str) -> Path:
    """Where a fitted conditioned codec is written, under the library root beside the other models."""
    return library_root / "models" / CODECS_DIRECTORY_NAME / f"{name}{CODEC_SUFFIX}"


def save_conditioned_codec(path: Path, model: ConditionedCodecModel, description: ConditionedCodecDescription) -> None:
    """Write the weights beside the description that says how to rebuild the network around them, in place whole."""
    stored = {"description": description.model_dump_json(), "state": model.state_dict()}
    write_atomically(path, lambda stream: torch.save(stored, stream))


def load_conditioned_codec(path: Path, *, library_root: Path, device: torch.device) -> ConditionedCodec:
    """Rebuild a fitted conditioned codec beside the descriptor it was trained to decode from.

    The descriptor is found by name and must still be the very file the codec was taught beside,
    since a codec decodes from what that descriptor says and nothing else.

    Raises:
        FileNotFoundError: no codec is stored at that path, or its descriptor is gone.
        ValueError: the descriptor stored under that name has changed since the codec was trained.
    """
    if not path.exists():
        raise FileNotFoundError(f"no conditioned codec is stored at {path}")

    stored = torch.load(path, map_location=device, weights_only=True)
    description = ConditionedCodecDescription.model_validate_json(str(stored["description"]))
    model = ConditionedCodecModel(description.shape).to(device)
    model.load_state_dict(stored["state"])
    model.eval()
    stored_descriptor = descriptor_path(library_root, name=description.descriptor)
    if stored_descriptor.is_file() and file_sha256(stored_descriptor) != description.descriptor_sha256:
        raise ValueError(
            f"the codec at {path} was trained beside another {description.descriptor} descriptor than the one "
            f"stored at {stored_descriptor} now; train the codec again beside it"
        )
    descriptor = load_descriptor(stored_descriptor, device=device)
    return ConditionedCodec(
        model=model, description=description, descriptor=descriptor, geometry=description.geometry, device=device
    )
