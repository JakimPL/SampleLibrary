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

    @cached_property
    def hash_array(self) -> NDArray[np.str_]:
        """The hashes as one array, which a tie between distances is broken on."""
        return np.asarray(self.hashes)

    @cached_property
    def squared_norms(self) -> NDArray[np.float64]:
        """Each row's squared length, which every search from any sample reuses."""
        norms: NDArray[np.float64] = np.einsum("ij,ij->i", self.matrix, self.matrix)
        return norms


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
    ascending hash, so the same inputs always resolve to the same ordering. Only the rows within
    the ``limit``-th distance are ordered, and the distances come from one product against the
    whole matrix, so a search costs one pass over the catalog.

    Raises:
        KeyError: if ``target_hash`` has no vector among these.
    """
    target_row = vectors.row_by_hash[target_hash]
    target = vectors.matrix[target_row]
    squared = vectors.squared_norms - 2.0 * (vectors.matrix @ target) + vectors.squared_norms[target_row]
    distances = np.sqrt(np.clip(squared, 0.0, None))
    distances[target_row] = np.inf
    kept = min(limit, len(vectors.hashes) - 1)
    if kept <= 0:
        return ()

    threshold = np.partition(distances, kept - 1)[kept - 1]
    candidates = np.flatnonzero(distances <= threshold)
    # Sorted on the distance first and the hash second: `lexsort` reads its keys back to front.
    order = candidates[np.lexsort((vectors.hash_array[candidates], distances[candidates]))]
    return tuple((vectors.hashes[row], float(distances[row])) for row in order[:kept])
