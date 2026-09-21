from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from numpy.typing import NDArray
from pydantic import BaseModel

from samplecore.models.base import FROZEN
from samplecore.storage.atomic import write_atomically
from sampledescriptor.canonicalizers import Canonicalizer
from sampledescriptor.descriptors.grid_descriptor import GridDescriptor
from sampledescriptor.descriptors.pooling import canonical_duration, pool_bands
from sampledescriptor.descriptors.shape import DescriptorShape
from sampledescriptor.geometry import GridGeometry
from sampledescriptor.images import SoundImage
from sampledescriptor.registries import canonicalizer_for_geometry
from samplemorph.canonicalizers.common import prepare_mono


class DescriptorDescription(BaseModel):
    """What a fitted descriptor is, recorded beside its weights so a file explains itself.

    The geometry travels with the model because the network reads one grid shape pooled one way,
    and a later change to the defaults must leave a stored descriptor readable as it was trained.
    """

    model_config = FROZEN

    canonicalizer: str
    geometry: GridGeometry
    bands_per_semitone: int
    shape: DescriptorShape
    teacher_experiment_id: int
    epochs: int
    trained_sample_count: int
    best_validation_loss: float


@dataclass(frozen=True)
class LearnedDescriptor:
    """Describes a sound with a network taught what the teacher hears and what the labels say.

    It reads a canonical image, so it inherits the alignment that makes a retuning a translation,
    and it reads a waveform by canonicalizing it first, which is the form the cloud's extraction
    pipeline hands it.
    """

    model: GridDescriptor
    description: DescriptorDescription
    canonicalizer: Canonicalizer
    device: torch.device

    @property
    def size(self) -> int:
        return self.description.shape.embedding_size

    def describe(self, image: SoundImage) -> NDArray[np.float64]:
        vector: NDArray[np.float64] = self.describe_many((image,))[0]
        return vector

    def describe_many(self, images: tuple[SoundImage, ...]) -> NDArray[np.float64]:
        """One vector per image, computed in one pass so a batch of images costs one forward."""
        grids = np.stack([pool_bands(image.grid, band_count=self.description.shape.band_count) for image in images])
        durations = np.array([canonical_duration(image.conditioners) for image in images], dtype=np.float32)
        with torch.no_grad():
            vectors = self.model(torch.from_numpy(grids).to(self.device), torch.from_numpy(durations).to(self.device))
        described: NDArray[np.float64] = vectors.cpu().numpy().astype(np.float64)
        return described

    def extract(self, waveform: NDArray[np.float64]) -> NDArray[np.float64]:
        """The cloud's extractor protocol: describe a stored waveform."""
        return self.describe(self.canonicalizer.canonicalize(prepare_mono(waveform)))


def save_descriptor(path: Path, model: GridDescriptor, description: DescriptorDescription) -> None:
    """Write the weights beside the description that says how to rebuild the network around them, in place whole."""
    stored = {"description": description.model_dump_json(), "state": model.state_dict()}
    write_atomically(path, lambda stream: torch.save(stored, stream))


def load_descriptor(path: Path, *, device: torch.device) -> LearnedDescriptor:
    """Rebuild a fitted descriptor around the very axis it was trained on.

    Raises:
        FileNotFoundError: no descriptor is stored at that path.
    """
    if not path.exists():
        raise FileNotFoundError(f"no descriptor is stored at {path}")

    stored = torch.load(path, map_location=device, weights_only=True)
    description = DescriptorDescription.model_validate_json(str(stored["description"]))
    model = GridDescriptor(description.shape).to(device)
    model.load_state_dict(stored["state"])
    model.eval()
    return LearnedDescriptor(
        model=model,
        description=description,
        canonicalizer=canonicalizer_for_geometry(description.geometry),
        device=device,
    )
