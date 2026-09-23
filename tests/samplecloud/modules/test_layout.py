from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.spatial.distance import pdist, squareform

from samplecloud.modules.layout import fit_module_plane, preservation

MODULES_PER_GROUP = 10
GROUP_OFFSET = 50.0


def _two_groups() -> NDArray[np.float32]:
    generator = np.random.default_rng(0)
    points = generator.normal(size=(2 * MODULES_PER_GROUP, 8))
    points[MODULES_PER_GROUP:] += GROUP_OFFSET
    distances: NDArray[np.float32] = squareform(pdist(points)).astype(np.float32)
    return distances


def test_two_groups_of_modules_land_apart_on_the_plane() -> None:
    coordinates = fit_module_plane(_two_groups(), n_neighbors=5)

    planar = squareform(pdist(coordinates))
    within = planar[:MODULES_PER_GROUP, :MODULES_PER_GROUP].max()
    between = planar[:MODULES_PER_GROUP, MODULES_PER_GROUP:].min()
    assert within < between


def test_preservation_scores_fall_within_their_ranges() -> None:
    distances = _two_groups()

    scores = preservation(distances, fit_module_plane(distances, n_neighbors=5))

    assert -1.0 <= scores.distance_correlation <= 1.0
    assert 0.0 <= scores.trustworthiness <= 1.0


def test_a_plane_that_is_the_distances_themselves_preserves_them_perfectly() -> None:
    points = np.random.default_rng(1).normal(size=(12, 2)).astype(np.float32)
    distances: NDArray[np.float32] = squareform(pdist(points)).astype(np.float32)

    scores = preservation(distances, points)

    assert scores.distance_correlation == 1.0
    assert scores.trustworthiness == 1.0
