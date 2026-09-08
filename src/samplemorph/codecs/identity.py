from __future__ import annotations

import numpy as np

from samplemorph.geometry import Geometry
from samplemorph.images import SampleLatent, SoundImage


class IdentityCodec:
    """Carries the whole grid as its latent, so encoding and decoding return exactly what they got.

    This is the floor every other codec is read against. Because it loses nothing, a reconstruction
    made through it measures what the frequency axis, the fixed grid and the phase estimate cost on
    their own -- which is what makes the loss a real codec adds attributable to that codec.
    """

    def __init__(self, geometry: Geometry) -> None:
        self._geometry = geometry

    @property
    def latent_size(self) -> int:
        band_count, time_columns = self._geometry.grid_shape
        return band_count * time_columns

    def encode(self, image: SoundImage) -> SampleLatent:
        return SampleLatent(
            values=image.grid.reshape(-1).copy(),
            conditioners=image.conditioners,
            geometry=self._geometry,
        )

    def decode(self, latent: SampleLatent) -> SoundImage:
        grid = np.clip(latent.values.reshape(self._geometry.grid_shape), 0.0, 1.0)
        return SoundImage(grid=grid, conditioners=latent.conditioners, geometry=self._geometry)
