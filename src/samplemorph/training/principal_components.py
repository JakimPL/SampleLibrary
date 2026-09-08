from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import numpy as np
from sklearn.decomposition import PCA

from samplemorph.codecs.principal_components import PrincipalComponentCodec
from samplemorph.geometry import Geometry
from samplemorph.images import SoundImage

DEFAULT_LATENT_SIZE: Final[int] = 256
DEFAULT_RANDOM_SEED: Final[int] = 0


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

    def fit(self, images: Sequence[SoundImage]) -> PrincipalComponentCodec:
        """Fit a codec to `images`.

        Raises:
            ValueError: fewer images were offered than the latent size asks for, which leaves the
                projection short of the directions it claims to carry.
        """
        if len(images) < self._latent_size:
            raise ValueError(
                f"fitting {self._latent_size} components asks for at least that many images, got {len(images)}"
            )

        matrix = np.stack([image.grid.reshape(-1) for image in images])
        decomposition = PCA(n_components=self._latent_size, svd_solver="randomized", random_state=self._random_seed)
        decomposition.fit(matrix)
        return PrincipalComponentCodec(
            mean=np.asarray(decomposition.mean_, dtype=np.float64),
            components=np.asarray(decomposition.components_, dtype=np.float64),
            explained_variance_ratio=np.asarray(decomposition.explained_variance_ratio_, dtype=np.float64),
            geometry=self._geometry,
        )
