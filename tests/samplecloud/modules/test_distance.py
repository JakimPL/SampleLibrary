from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest
from numpy.typing import NDArray

from samplecloud.modules.distance import BATCH_MEMBER_COUNT, chamfer_distances
from samplecloud.modules.membership import ModuleSampleSets, module_sample_sets
from samplecore.spectral_distance import SpectralVectors

KICK = "a" * 64
SNARE = "b" * 64
PAD = "c" * 64
BELL = "d" * 64
SPECTRAL = SpectralVectors(
    hashes=(KICK, SNARE, PAD, BELL),
    matrix=np.array([[0.0, 0.0], [3.0, 0.0], [0.0, 4.0], [30.0, 40.0]]),
)


def _distances(members: dict[str, frozenset[str]]) -> tuple[ModuleSampleSets, NDArray[np.float32]]:
    sets = module_sample_sets(members, SPECTRAL)
    return sets, chamfer_distances(sets)


def _distance_between(members: dict[str, frozenset[str]], first: str, second: str) -> float:
    sets, distances = _distances(members)
    return float(distances[sets.module_hashes.index(first), sets.module_hashes.index(second)])


@dataclass(frozen=True)
class DistanceCase:
    name: str
    first: frozenset[str]
    second: frozenset[str]
    expected: float


DISTANCE_CASES = (
    DistanceCase(name="identical sets", first=frozenset({KICK, PAD}), second=frozenset({KICK, PAD}), expected=0.0),
    DistanceCase(
        name="one extra sample costs its distance over twice the larger size",
        first=frozenset({KICK, SNARE}),
        second=frozenset({KICK, SNARE, PAD}),
        expected=4.0 / (2 * 3),
    ),
    DistanceCase(
        name="disjoint single samples lie their own distance apart",
        first=frozenset({KICK}),
        second=frozenset({PAD}),
        expected=4.0,
    ),
    DistanceCase(
        name="both directions are averaged",
        first=frozenset({KICK}),
        second=frozenset({SNARE, PAD}),
        expected=0.5 * (3.0 + (3.0 + 4.0) / 2),
    ),
)


@pytest.mark.parametrize("case", DISTANCE_CASES, ids=[case.name for case in DISTANCE_CASES])
def test_chamfer_distance_between_two_modules(case: DistanceCase) -> None:
    first_module, second_module = "1" * 64, "2" * 64

    distance = _distance_between({first_module: case.first, second_module: case.second}, first_module, second_module)

    assert distance == pytest.approx(case.expected, rel=1e-5)


def test_distances_are_symmetric_with_a_zero_diagonal() -> None:
    _, distances = _distances(
        {
            "1" * 64: frozenset({KICK, SNARE}),
            "2" * 64: frozenset({PAD, BELL}),
            "3" * 64: frozenset({KICK, BELL}),
        }
    )

    np.testing.assert_array_equal(distances, distances.T)
    np.testing.assert_array_equal(np.diag(distances), np.zeros(3))


def test_batches_measure_as_one_whole() -> None:
    generator = np.random.default_rng(0)
    hashes = tuple(format(index + 1, "064x") for index in range(BATCH_MEMBER_COUNT + 40))
    spectral = SpectralVectors(hashes=hashes, matrix=generator.normal(size=(len(hashes), 3)))
    members = {
        format(module, "064x"): frozenset(hashes[module * 7 : module * 7 + 1 + module % 9])
        for module in range(len(hashes) // 7)
    }
    sets = module_sample_sets(members, spectral)

    distances = chamfer_distances(sets)

    first, second = 3, len(sets.module_hashes) - 2
    first_vectors = sets.vectors[sets.member_rows[first]].astype(np.float64)
    second_vectors = sets.vectors[sets.member_rows[second]].astype(np.float64)
    pairwise = np.linalg.norm(first_vectors[:, None, :] - second_vectors[None, :, :], axis=2)
    expected = 0.5 * (pairwise.min(axis=1).mean() + pairwise.min(axis=0).mean())
    assert distances[first, second] == pytest.approx(expected, rel=1e-4)


def test_a_distant_sample_moves_a_module_farther_than_a_close_one() -> None:
    base = frozenset({KICK, SNARE})
    members = {"1" * 64: base, "2" * 64: base | {PAD}, "3" * 64: base | {BELL}}

    with_pad = _distance_between(members, "1" * 64, "2" * 64)
    with_bell = _distance_between(members, "1" * 64, "3" * 64)

    assert 0.0 < with_pad < with_bell


def test_no_modules_give_an_empty_matrix() -> None:
    _, distances = _distances({})

    assert distances.shape == (0, 0)
