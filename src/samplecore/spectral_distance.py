from __future__ import annotations

import numpy as np


def euclidean_distance(vector_a: tuple[float, ...], vector_b: tuple[float, ...]) -> float:
    """The straight-line distance between two standardized spectral feature vectors.

    Raises:
        ValueError: if the two vectors do not have the same length.
    """
    if len(vector_a) != len(vector_b):
        raise ValueError(f"vectors have different lengths: {len(vector_a)} != {len(vector_b)}")

    return float(np.linalg.norm(np.array(vector_a) - np.array(vector_b)))


def nearest_neighbors(
    target_hash: str, vectors_by_hash: dict[str, tuple[float, ...]], *, limit: int
) -> tuple[tuple[str, float], ...]:
    """The ``limit`` sample hashes whose vector sits closest to ``target_hash``'s, nearest first.

    ``target_hash`` itself is excluded from its own neighbor list. A tied distance is broken by
    ascending hash, so the same inputs always resolve to the same ordering.

    Raises:
        KeyError: if ``target_hash`` has no entry in ``vectors_by_hash``.
    """
    target_vector = vectors_by_hash[target_hash]
    neighbors = sorted(
        (
            (sample_hash, euclidean_distance(target_vector, vector))
            for sample_hash, vector in vectors_by_hash.items()
            if sample_hash != target_hash
        ),
        key=lambda neighbor: (neighbor[1], neighbor[0]),
    )
    return tuple(neighbors[:limit])
