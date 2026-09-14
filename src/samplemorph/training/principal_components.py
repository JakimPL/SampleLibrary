from __future__ import annotations

from collections.abc import Iterable
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.codecs.principal_components import PrincipalComponentCodec
from samplemorph.geometry import Geometry
from samplemorph.images import SoundImage
from samplemorph.training.run_settings import DEFAULT_RANDOM_SEED

DEFAULT_LATENT_SIZE: Final[int] = 256


def stack_grids(images: Iterable[SoundImage], *, count: int, geometry: Geometry) -> NDArray[np.float32]:
    """Lay `count` grids out as the rows of one single-precision matrix, filled as the images arrive.

    Only the image being laid out is held beside the matrix, so a fit over thousands of grids needs
    the matrix and little more.

    Raises:
        ValueError: the images number other than `count`.
    """
    bands, columns = geometry.grid_shape
    matrix = np.empty((count, bands * columns), dtype=np.float32)
    filled = 0
    for row, image in enumerate(images):
        if row >= count:
            raise ValueError(f"more than the {count} grids a matrix was laid out for arrived")
        matrix[row] = image.grid.reshape(-1)
        filled = row + 1
    if filled != count:
        raise ValueError(f"{filled} grids arrived for a matrix laid out for {count}")
    return matrix


class PrincipalComponentTrainer:
    """Finds the directions a body of grids varies along most, by singular value decomposition.

    Grids are centered and left otherwise as they are. They already share one unit -- normalized
    decibels within a fixed dynamic range -- so per-pixel rescaling would divide the always-quiet
    bands by a near-zero spread and turn their quantization noise into apparent signal.
    """

    def __init__(
        self,
        geometry: Geometry,
        *,
        latent_size: int = DEFAULT_LATENT_SIZE,
        random_seed: int = DEFAULT_RANDOM_SEED,
    ) -> None:
        self._geometry = geometry
        self._latent_size = latent_size
        self._random_seed = random_seed

    def fit(self, grids: NDArray[np.float32]) -> PrincipalComponentCodec:
        """Fit a codec to the grids laid out one per row, as `stack_grids` lays them.

        The matrix is centered in place, so it holds the centered grids once the fit returns.

        Raises:
            ValueError: fewer grids were offered than the latent size asks for, which leaves the
                projection short of the directions it claims to carry.
        """
        if grids.shape[0] < self._latent_size:
            raise ValueError(
                f"fitting {self._latent_size} components asks for at least that many images, got {grids.shape[0]}"
            )

        # pylint: disable=import-outside-toplevel
        from sklearn.decomposition import PCA

        decomposition = PCA(
            n_components=self._latent_size, svd_solver="randomized", random_state=self._random_seed, copy=False
        )
        decomposition.fit(grids)
        return PrincipalComponentCodec(
            mean=np.asarray(decomposition.mean_, dtype=np.float32),
            components=np.asarray(decomposition.components_, dtype=np.float32),
            explained_variance_ratio=np.asarray(decomposition.explained_variance_ratio_, dtype=np.float32),
            geometry=self._geometry,
        )
