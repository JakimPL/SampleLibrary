from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class SpectralVectors:
    """Every embedded sample's standardized vector, as one matrix a search can sweep in one pass.

    ``hashes`` names the sample each row belongs to, in the matrix's own row order. Holding the
    vectors together rather than one per model is what lets a neighbor search measure a whole
    catalog at once, which is arithmetic a hundred thousand separate distance calls cannot reach.
    """

    hashes: tuple[str, ...]
    matrix: NDArray[np.float64]

    @cached_property
    def row_by_hash(self) -> dict[str, int]:
        """Which row of the matrix each sample's vector sits in."""
        return {sample_hash: row for row, sample_hash in enumerate(self.hashes)}


def euclidean_distance(vector_a: tuple[float, ...], vector_b: tuple[float, ...]) -> float:
    """The straight-line distance between two standardized spectral feature vectors.

    Raises:
        ValueError: if the two vectors do not have the same length.
    """
    if len(vector_a) != len(vector_b):
        raise ValueError(f"vectors have different lengths: {len(vector_a)} != {len(vector_b)}")

    return float(np.linalg.norm(np.array(vector_a) - np.array(vector_b)))


def nearest_neighbors(target_hash: str, vectors: SpectralVectors, *, limit: int) -> tuple[tuple[str, float], ...]:
    """The ``limit`` sample hashes whose vector sits closest to ``target_hash``'s, nearest first.

    ``target_hash`` itself is excluded from its own neighbor list. A tied distance is broken by
    ascending hash, so the same inputs always resolve to the same ordering.

    Raises:
        KeyError: if ``target_hash`` has no vector among these.
    """
    target_row = vectors.row_by_hash[target_hash]
    distances = np.linalg.norm(vectors.matrix - vectors.matrix[target_row], axis=1)
    # Sorted on the distance first and the hash second: `lexsort` reads its keys back to front.
    order = np.lexsort((np.asarray(vectors.hashes), distances))
    neighbors = ((vectors.hashes[row], float(distances[row])) for row in order[: limit + 1] if row != target_row)
    return tuple(neighbors)[:limit]
