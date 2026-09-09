from __future__ import annotations

import numpy as np
import pytest

from samplecore.spectral_distance import SpectralVectors, euclidean_distance, nearest_neighbors

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _vectors(vectors_by_hash: dict[str, tuple[float, ...]]) -> SpectralVectors:
    """The matrix form a search reads, built from the vectors a test states by hash."""
    return SpectralVectors(
        hashes=tuple(vectors_by_hash),
        matrix=np.array(list(vectors_by_hash.values()), dtype=np.float64),
    )


def test_euclidean_distance_of_a_vector_to_itself_is_zero() -> None:
    assert euclidean_distance((1.0, 2.0, 3.0), (1.0, 2.0, 3.0)) == 0.0


def test_euclidean_distance_matches_a_known_right_triangle() -> None:
    assert euclidean_distance((0.0, 0.0), (3.0, 4.0)) == 5.0


def test_euclidean_distance_is_symmetric() -> None:
    first = (1.0, -2.0, 0.5)
    second = (-3.0, 4.0, 2.0)

    assert euclidean_distance(first, second) == euclidean_distance(second, first)


def test_euclidean_distance_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="different lengths"):
        euclidean_distance((1.0, 2.0), (1.0, 2.0, 3.0))


def test_nearest_neighbors_excludes_the_target_itself() -> None:
    vectors_by_hash = {HASH_A: (0.0, 0.0), HASH_B: (1.0, 0.0)}

    neighbors = nearest_neighbors(HASH_A, _vectors(vectors_by_hash), limit=10)

    assert neighbors == ((HASH_B, 1.0),)


def test_nearest_neighbors_orders_by_ascending_distance() -> None:
    vectors_by_hash = {HASH_A: (0.0, 0.0), HASH_B: (5.0, 0.0), HASH_C: (1.0, 0.0)}

    neighbors = nearest_neighbors(HASH_A, _vectors(vectors_by_hash), limit=10)

    assert [neighbor_hash for neighbor_hash, _ in neighbors] == [HASH_C, HASH_B]


def test_nearest_neighbors_breaks_a_tied_distance_by_ascending_hash() -> None:
    vectors_by_hash = {HASH_A: (0.0, 0.0), HASH_C: (1.0, 0.0), HASH_B: (0.0, 1.0)}

    neighbors = nearest_neighbors(HASH_A, _vectors(vectors_by_hash), limit=10)

    assert [neighbor_hash for neighbor_hash, _ in neighbors] == [HASH_B, HASH_C]


def test_nearest_neighbors_respects_the_limit() -> None:
    vectors_by_hash = {HASH_A: (0.0, 0.0), HASH_B: (1.0, 0.0), HASH_C: (2.0, 0.0)}

    neighbors = nearest_neighbors(HASH_A, _vectors(vectors_by_hash), limit=1)

    assert neighbors == ((HASH_B, 1.0),)


def test_nearest_neighbors_raises_for_an_unknown_target() -> None:
    with pytest.raises(KeyError):
        nearest_neighbors(HASH_A, _vectors({HASH_B: (0.0, 0.0)}), limit=10)
