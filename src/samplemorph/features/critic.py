from __future__ import annotations

from torch import Tensor, nn

from samplemorph.features.shape import FeatureShape
from samplemorph.features.stages import downsampling_trunk, padded


class InterpolationCritic(nn.Module):
    """Reads a decoded grid and answers how far along a latent line between two sounds it was decoded from.

    It is taught to answer the share a latent interpolant was mixed at, from 0 at an end to 0.5
    at the midpoint, and 0 on a sound read back whole; an autoencoder taught to make its
    interpolants read 0 is taught to decode every point of a line as one sound. It reads the grid
    through the same stages as the encoder.
    """

    def __init__(self, shape: FeatureShape) -> None:
        super().__init__()
        self.shape = shape
        self.trunk = downsampling_trunk(shape)
        self.head = nn.Linear(shape.deepest_size, 1)

    def forward(self, grids: Tensor) -> Tensor:
        # grids: (batch, bands, columns) -> (batch,)
        features = self.trunk(padded(grids, shape=self.shape)[:, None])
        scores: Tensor = self.head(features.flatten(start_dim=1))[:, 0]
        return scores
