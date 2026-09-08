from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from samplemorph.geometry import Geometry
from samplemorph.images import SampleLatent, SoundImage


class PrincipalComponentCodec:
    """Projects a grid onto the directions a body of grids varies along most, and back.

    The projection is linear and its inverse is the transpose, so a latent of full rank returns the
    grid exactly and a shorter one returns the part of it the retained directions span. That makes
    this the honest first codec: what a reconstruction loses is the projection, stated by the
    explained-variance figure the fit reports, rather than an opaque model's judgment.

    Decoding clips the result back into ``[0, 1]``, since a projection of a point between two grids
    can land just outside the range a normalized image occupies. The clip is what keeps an
    interpolated latent on the manifold a grid describes.
    """

    def __init__(
        self,
        *,
        mean: NDArray[np.float64],
        components: NDArray[np.float64],
        explained_variance_ratio: NDArray[np.float64],
        geometry: Geometry,
    ) -> None:
        self._mean = mean
        self._components = components
        self._explained_variance_ratio = explained_variance_ratio
        self._geometry = geometry

    @property
    def latent_size(self) -> int:
        return int(self._components.shape[0])

    @property
    def mean(self) -> NDArray[np.float64]:
        return self._mean

    @property
    def components(self) -> NDArray[np.float64]:
        return self._components

    @property
    def explained_variance_ratio(self) -> NDArray[np.float64]:
        """The share of the fitted body's variance each retained direction accounts for."""
        return self._explained_variance_ratio

    @property
    def explained_variance(self) -> float:
        """The share of the fitted body's variance the whole latent accounts for."""
        return float(self._explained_variance_ratio.sum())

    def encode(self, image: SoundImage) -> SampleLatent:
        centered = image.grid.reshape(-1) - self._mean
        return SampleLatent(
            values=self._components @ centered,
            conditioners=image.conditioners,
            geometry=self._geometry,
        )

    def decode(self, latent: SampleLatent) -> SoundImage:
        flat = latent.values @ self._components + self._mean
        grid = np.clip(flat.reshape(self._geometry.grid_shape), 0.0, 1.0)
        return SoundImage(grid=grid, conditioners=latent.conditioners, geometry=self._geometry)
