from __future__ import annotations

import pydantic
import pytest

from samplecore.models.morph import (
    MORPH_WEIGHT_STEPS,
    HeardMorphPoint,
    MorphPoint,
    morph_weights,
)

FIRST = "a" * 64
SECOND = "b" * 64
FIRST_RATE_HZ = 8_363
SECOND_RATE_HZ = 16_726


@pytest.mark.parametrize("weight", morph_weights())
def test_every_weight_on_the_grid_makes_a_point(weight: float) -> None:
    point = MorphPoint(first=FIRST, second=SECOND, weight=weight)

    assert point.step == round(weight * MORPH_WEIGHT_STEPS)


@pytest.mark.parametrize("weight", (0.305, 1.5, -0.01))
def test_a_weight_off_the_grid_or_outside_the_unit_interval_is_refused(weight: float) -> None:
    with pytest.raises(pydantic.ValidationError):
        MorphPoint(first=FIRST, second=SECOND, weight=weight)


def test_the_grid_runs_from_the_first_sample_to_the_second() -> None:
    weights = morph_weights()

    assert weights[0] == 0.0
    assert weights[-1] == 1.0
    assert len(weights) == MORPH_WEIGHT_STEPS + 1
    assert all(later > earlier for earlier, later in zip(weights, weights[1:], strict=False))


def test_a_point_is_hashable_so_a_cache_can_key_on_it() -> None:
    point = MorphPoint(first=FIRST, second=SECOND, weight=0.5)

    assert hash(point) == hash(MorphPoint(first=FIRST, second=SECOND, weight=0.5))
    assert point != MorphPoint(first=SECOND, second=FIRST, weight=0.5)


def test_a_heard_point_is_named_by_its_rates_as_well() -> None:
    point = HeardMorphPoint(
        first=FIRST, second=SECOND, weight=0.5, first_rate_hz=FIRST_RATE_HZ, second_rate_hz=SECOND_RATE_HZ
    )
    same = HeardMorphPoint(
        first=FIRST, second=SECOND, weight=0.5, first_rate_hz=FIRST_RATE_HZ, second_rate_hz=SECOND_RATE_HZ
    )
    retuned = HeardMorphPoint(
        first=FIRST, second=SECOND, weight=0.5, first_rate_hz=FIRST_RATE_HZ, second_rate_hz=FIRST_RATE_HZ
    )

    assert hash(point) == hash(same)
    assert point != retuned


@pytest.mark.parametrize("rate_hz", (0, -FIRST_RATE_HZ))
def test_a_heard_point_refuses_a_rate_that_sounds_nothing(rate_hz: int) -> None:
    with pytest.raises(pydantic.ValidationError):
        HeardMorphPoint(first=FIRST, second=SECOND, weight=0.5, first_rate_hz=rate_hz, second_rate_hz=SECOND_RATE_HZ)
