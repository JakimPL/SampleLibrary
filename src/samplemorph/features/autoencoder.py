from __future__ import annotations

import torch
from torch import Tensor, nn

from samplemorph.features.shape import FeatureShape
from samplemorph.features.stages import downsampling_trunk, padded, upsampling_trunk


class GridEncoder(nn.Module):
    """Reads a pooled grid into one latent vector.

    The deepest map is flattened into the latent whole, so every coordinate can depend on where
    along the band axis and when along the grid a feature sits.
    """

    def __init__(self, shape: FeatureShape) -> None:
        super().__init__()
        self.shape = shape
        self.trunk = downsampling_trunk(shape)
        self.head = nn.Linear(shape.deepest_size, shape.latent_size)

    def forward(self, grids: Tensor) -> Tensor:
        # grids: (batch, bands, columns) -> (batch, latent)
        features = self.trunk(padded(grids, shape=self.shape)[:, None])
        latents: Tensor = self.head(features.flatten(start_dim=1))
        return latents


class GridDecoder(nn.Module):
    """Grows a latent vector back into a pooled grid, every cell in [0, 1] as the cache stores them."""

    def __init__(self, shape: FeatureShape) -> None:
        super().__init__()
        self.shape = shape
        self.head = nn.Linear(shape.latent_size, shape.deepest_size)
        self.trunk = upsampling_trunk(shape)
        self.output = nn.Conv2d(shape.width, 1, 1)

    def forward(self, latents: Tensor) -> Tensor:
        # latents: (batch, latent) -> (batch, bands, columns)
        deepest = self.head(latents).view(latents.shape[0], *self.shape.deepest_map)
        grown = torch.sigmoid(self.output(self.trunk(deepest)))[:, 0]
        return grown[:, : self.shape.band_count, : self.shape.time_columns]


class FeatureAutoencoder(nn.Module):
    """An encoder and a decoder over pooled grids, whose latent lines are what a morph walks."""

    def __init__(self, shape: FeatureShape) -> None:
        super().__init__()
        self.shape = shape
        self.encoder = GridEncoder(shape)
        self.decoder = GridDecoder(shape)

    def forward(self, grids: Tensor) -> Tensor:
        reconstructions: Tensor = self.decoder(self.encoder(grids))
        return reconstructions
