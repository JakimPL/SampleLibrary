from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel
from scipy.spatial.distance import pdist, squareform
from scipy.stats import spearmanr
from sklearn.manifold import trustworthiness

from samplecloud.reduce import RANDOM_SEED
from samplecore.models.base import FROZEN

PRECOMPUTED_METRIC: Final[str] = "precomputed"
TRUSTWORTHINESS_NEIGHBORS: Final[int] = 5


class LayoutPreservation(BaseModel):
    """How faithfully a plane keeps the module distances it was fit from.

    ``distance_correlation`` is the Spearman rank correlation between every pair's module distance
    and its distance on the plane, which reads how well the global arrangement survives.
    ``trustworthiness`` is 1 when every module's nearest neighbors on the plane are also its
    nearest neighbors by module distance, which reads how well the local arrangement survives.
    """

    model_config = FROZEN

    distance_correlation: float
    trustworthiness: float


def fit_module_plane(distances: NDArray[np.float32], *, n_neighbors: int) -> NDArray[np.float32]:
    """Lay modules out on a plane with UMAP fit straight from their pairwise distances."""
    # UMAP compiles its kernels as it is imported, which a run over too few modules spares itself here.
    import umap  # pylint: disable=import-outside-toplevel

    coordinates: NDArray[np.float32] = umap.UMAP(
        n_neighbors=n_neighbors, metric=PRECOMPUTED_METRIC, random_state=RANDOM_SEED, verbose=True
    ).fit_transform(distances)
    return coordinates


def preservation(distances: NDArray[np.float32], coordinates: NDArray[np.float32]) -> LayoutPreservation:
    """Score how well ``coordinates`` keep the pairwise ``distances``, both globally and among neighbors.

    The neighborhood trustworthiness weighs is bounded below half the module count, which the
    measure itself requires.
    """
    upper_triangle = np.triu_indices(len(distances), k=1)
    planar = squareform(pdist(coordinates))
    neighbors = max(1, min(TRUSTWORTHINESS_NEIGHBORS, (len(distances) - 1) // 2))
    return LayoutPreservation(
        distance_correlation=float(spearmanr(distances[upper_triangle], planar[upper_triangle]).statistic),
        trustworthiness=float(
            trustworthiness(distances, coordinates, n_neighbors=neighbors, metric=PRECOMPUTED_METRIC)
        ),
    )
