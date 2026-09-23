from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest
from numpy.typing import NDArray

from samplecloud.modules.distance import chamfer_distances, nearest_distances_to_modules
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
    return sets, chamfer_distances(sets, nearest_distances_to_modules(sets))


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


def test_a_module_holding_a_sample_lies_exactly_zero_from_it() -> None:
    sets = module_sample_sets({"1" * 64: frozenset({BELL, PAD}), "2" * 64: frozenset({BELL})}, SPECTRAL)

    nearest = nearest_distances_to_modules(sets)

    for column, rows in enumerate(sets.member_rows):
        np.testing.assert_array_equal(nearest[rows, column], np.zeros(len(rows)))


def test_a_distant_sample_moves_a_module_farther_than_a_close_one() -> None:
    base = frozenset({KICK, SNARE})
    members = {"1" * 64: base, "2" * 64: base | {PAD}, "3" * 64: base | {BELL}}

    with_pad = _distance_between(members, "1" * 64, "2" * 64)
    with_bell = _distance_between(members, "1" * 64, "3" * 64)

    assert 0.0 < with_pad < with_bell


def test_no_modules_give_an_empty_matrix() -> None:
    _, distances = _distances({})

    assert distances.shape == (0, 0)
