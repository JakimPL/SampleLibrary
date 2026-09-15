from __future__ import annotations

from dataclasses import dataclass

import pytest

from samplemorph.listening.comparing import ComparisonWeights, blind_folders, named_folders
from samplemorph.routes.kinds import RouteKind


@dataclass(frozen=True)
class RefusedWeightsCase:
    path: tuple[float, ...]
    listening: tuple[float, ...]


REFUSED_WEIGHTS_CASES = (
    RefusedWeightsCase(path=(0.0, 0.5), listening=()),
    RefusedWeightsCase(path=(0.25, 1.0), listening=()),
    RefusedWeightsCase(path=(0.0, 0.75, 0.5, 1.0), listening=()),
    RefusedWeightsCase(path=(0.0, 0.5, 1.0), listening=(0.25,)),
    RefusedWeightsCase(path=(0.0,), listening=()),
)


@pytest.mark.parametrize("case", REFUSED_WEIGHTS_CASES)
def test_weights_off_a_rising_path_from_zero_to_one_are_refused(case: RefusedWeightsCase) -> None:
    with pytest.raises(ValueError):
        ComparisonWeights(path=case.path, listening=case.listening)


def test_both_ends_and_every_listening_weight_are_written() -> None:
    weights = ComparisonWeights(path=(0.0, 0.25, 0.5, 0.75, 1.0), listening=(0.5,))

    assert weights.written == frozenset((0.0, 0.5, 1.0))


def test_blind_folders_deal_every_route_a_letter_of_its_own_by_seed() -> None:
    kinds = tuple(RouteKind)

    folders = blind_folders(kinds, random_seed=11)

    assert sorted(folders) == ["A", "B", "C"]
    assert folders == blind_folders(kinds, random_seed=11)
    assert set(folders).isdisjoint(named_folders(kinds))
