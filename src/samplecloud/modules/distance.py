from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from samplecloud.modules.membership import ModuleSampleSets


def nearest_distances_to_modules(sets: ModuleSampleSets) -> NDArray[np.float32]:
    """How far each sample lies from the closest sample of each module.

    Row ``sample`` and column ``module`` hold the smallest Euclidean distance between that sample's
    vector and any vector of that module. A module's own samples lie at exactly 0 from it, so two
    modules holding the same set of samples come out exactly 0 apart once the distances are averaged.
    """
    vectors = sets.vectors
    squared_norms = np.einsum("ij,ij->i", vectors, vectors)
    nearest = np.empty((len(vectors), len(sets.module_hashes)), dtype=np.float32)
    for column, rows in enumerate(sets.member_rows):
        # (samples, members): squared distances from every sample to each of this module's samples.
        squared = squared_norms[:, None] - 2.0 * (vectors @ vectors[rows].T) + squared_norms[rows][None, :]
        nearest[:, column] = np.sqrt(np.clip(squared.min(axis=1), 0.0, None))
        nearest[rows, column] = 0.0
    return nearest


def chamfer_distances(sets: ModuleSampleSets, nearest: NDArray[np.float32]) -> NDArray[np.float32]:
    """The symmetric Chamfer distance between every pair of modules' sample sets.

    The directed distance from module A to module B is the mean, over A's samples, of each one's
    distance to B's closest sample; the result averages both directions. Averaging over each
    module's own samples keeps modules of different sizes comparable: a module that adds one sample
    to another's set lies that sample's distance divided by twice its own size away.
    """
    if not sets.member_rows:
        return np.zeros((0, 0), dtype=np.float32)

    # (modules, modules): row A, column B holds the directed distance from A to B.
    directed = np.stack([nearest[rows].mean(axis=0) for rows in sets.member_rows])
    distances: NDArray[np.float32] = (0.5 * (directed + directed.T)).astype(np.float32)
    return distances
