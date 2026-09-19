from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import torch
from numpy.typing import NDArray
from pydantic import BaseModel

from samplecore.models.base import FROZEN
from samplecore.storage.atomic import write_atomically
from samplemorph.features.autoencoder import FeatureAutoencoder
from samplemorph.features.critic import InterpolationCritic
from samplemorph.features.shape import FeatureShape
from samplemorph.geometry import Geometry

DESCRIPTION_KEY: Final[str] = "description"
AUTOENCODER_KEY: Final[str] = "autoencoder"
CRITIC_KEY: Final[str] = "critic"
READING_BATCH_SIZE: Final[int] = 256


class FeatureDescription(BaseModel):
    """What a trained feature model is and where it came from, recorded beside its weights.

    `cache` names the grid cache it was taught on, whose axis and pooling every grid it reads must
    share. `validation_hashes` are the samples it was judged on and never taught, whole equivalence
    classes at a time, which is where a reading of the model draws its sounds from.
    """

    model_config = FROZEN

    cache: str
    canonicalizer: str
    geometry: Geometry
    bands_per_semitone: int
    shape: FeatureShape
    critic_weight: float
    critic_mix: float
    random_seed: int
    epochs: int
    trained_sample_count: int
    best_validation_loss: float
    validation_hashes: tuple[str, ...]


@dataclass(frozen=True)
class StoredFeatures:
    """A trained autoencoder and its critic, read and written as arrays of pooled grids.

    Shapes: grids are ``(count, bands, columns)``, latents ``(count, latent size)`` and scores ``(count,)``.
    """

    autoencoder: FeatureAutoencoder
    critic: InterpolationCritic
    description: FeatureDescription
    device: torch.device

    def encode(self, grids: NDArray[np.float32]) -> NDArray[np.float32]:
        return self._read(self.autoencoder.encoder, grids)

    def decode(self, latents: NDArray[np.float32]) -> NDArray[np.float32]:
        return self._read(self.autoencoder.decoder, latents)

    def score(self, grids: NDArray[np.float32]) -> NDArray[np.float32]:
        """The critic's reading of every grid: about 0 for a sound, up to 0.5 for a midpoint that shows."""
        return self._read(self.critic, grids)

    def _read(self, network: torch.nn.Module, inputs: NDArray[np.float32]) -> NDArray[np.float32]:
        outputs = []
        with torch.no_grad():
            for start in range(0, len(inputs), READING_BATCH_SIZE):
                batch = torch.from_numpy(np.ascontiguousarray(inputs[start : start + READING_BATCH_SIZE]))
                outputs.append(network(batch.to(self.device, dtype=torch.float32)).cpu().numpy())
        read: NDArray[np.float32] = np.concatenate(outputs).astype(np.float32)
        return read


def save_features(
    path: Path, *, autoencoder: FeatureAutoencoder, critic: InterpolationCritic, description: FeatureDescription
) -> None:
    """Write both networks beside the description that rebuilds them, in place whole."""
    stored = {
        DESCRIPTION_KEY: description.model_dump_json(),
        AUTOENCODER_KEY: autoencoder.state_dict(),
        CRITIC_KEY: critic.state_dict(),
    }
    write_atomically(path, lambda stream: torch.save(stored, stream))


def load_features(path: Path, *, device: torch.device) -> StoredFeatures:
    """Rebuild a trained feature model on `device`, ready to read.

    Raises:
        FileNotFoundError: no feature model is stored at that path.
    """
    if not path.exists():
        raise FileNotFoundError(f"no feature model is stored at {path}")

    stored = torch.load(path, map_location=device, weights_only=True)
    description = FeatureDescription.model_validate_json(str(stored[DESCRIPTION_KEY]))
    autoencoder = FeatureAutoencoder(description.shape).to(device)
    autoencoder.load_state_dict(stored[AUTOENCODER_KEY])
    autoencoder.eval()
    critic = InterpolationCritic(description.shape).to(device)
    critic.load_state_dict(stored[CRITIC_KEY])
    critic.eval()
    return StoredFeatures(autoencoder=autoencoder, critic=critic, description=description, device=device)
