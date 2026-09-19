from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from samplemorph.canonicalizers.common import PreparedMono
from samplemorph.descriptors.pooling import pool_bands
from samplemorph.measurement.ladders.tones import ResonantTone
from samplemorph.measurement.ladders.truth import (
    Ladder,
    LadderFamily,
    LadderRecipe,
    draw_synthetic_ends,
    ladder_weights,
    synthetic_ladder,
)
from tests.samplemorph.measurement.ladders.conftest import AXIS, INTERVAL_SEMITONES, WEIGHTS

INTERVALS = (3.0, 7.0)


@dataclass(frozen=True)
class MotionCase:
    family: LadderFamily
    fundamental_ratio: float
    resonance_ratio: float


def test_a_retuned_ladder_is_centered_on_the_stored_reading_the_cache_holds(
    retuned: Ladder, tone_mono: PreparedMono, recipe: LadderRecipe
) -> None:
    stored = pool_bands(recipe.canonicalizer.canonicalize(tone_mono).grid, band_count=AXIS.band_count)

    assert np.array_equal(retuned.truth[len(WEIGHTS) // 2], stored)
    assert retuned.truth.shape == (len(WEIGHTS), AXIS.band_count, AXIS.geometry.time_columns)
    assert retuned.is_translation


def test_the_weights_run_evenly_from_one_end_to_the_other() -> None:
    weights = ladder_weights(5)

    assert weights == (0.0, 0.25, 0.5, 0.75, 1.0)


def test_a_ladder_with_no_step_between_its_ends_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one step"):
        ladder_weights(2)


def test_a_tone_between_two_stands_on_the_geometric_line_between_their_positions() -> None:
    low = ResonantTone(fundamental_hz=100.0, resonance_hz=1000.0)
    high = ResonantTone(fundamental_hz=400.0, resonance_hz=4000.0)

    middle = low.between(high, weight=0.5)

    assert middle == ResonantTone(fundamental_hz=pytest.approx(200.0), resonance_hz=pytest.approx(2000.0))


@pytest.mark.parametrize(
    "case",
    [
        MotionCase(LadderFamily.PITCH, fundamental_ratio=1.0, resonance_ratio=0.0),
        MotionCase(LadderFamily.RESONANCE, fundamental_ratio=0.0, resonance_ratio=1.0),
        MotionCase(LadderFamily.CONTRARY, fundamental_ratio=1.0, resonance_ratio=-1.0),
    ],
    ids=("pitch", "resonance", "contrary"),
)
def test_each_synthetic_family_moves_its_own_feature_by_the_interval(case: MotionCase) -> None:
    drawn = draw_synthetic_ends(case.family, count=len(INTERVALS), intervals=INTERVALS, random_seed=0)

    for ends, interval in zip(drawn, INTERVALS, strict=True):
        assert ends.interval_semitones == interval
        assert 12.0 * np.log2(ends.second.fundamental_hz / ends.first.fundamental_hz) == pytest.approx(
            case.fundamental_ratio * interval
        )
        assert 12.0 * np.log2(ends.second.resonance_hz / ends.first.resonance_hz) == pytest.approx(
            case.resonance_ratio * interval
        )


def test_a_draw_repeats_under_its_seed_and_each_family_draws_its_own_tones() -> None:
    pitch = draw_synthetic_ends(LadderFamily.PITCH, count=2, intervals=INTERVALS, random_seed=3)

    assert pitch == draw_synthetic_ends(LadderFamily.PITCH, count=2, intervals=INTERVALS, random_seed=3)
    assert (
        pitch[0].first
        != draw_synthetic_ends(LadderFamily.RESONANCE, count=2, intervals=INTERVALS, random_seed=3)[0].first
    )


def test_a_family_read_from_the_library_is_not_synthesized() -> None:
    with pytest.raises(ValueError, match="read from the library"):
        draw_synthetic_ends(LadderFamily.RETUNED, count=1, intervals=INTERVALS, random_seed=0)


def test_a_synthetic_ladder_holds_its_two_tones_at_its_ends(recipe: LadderRecipe) -> None:
    (ends,) = draw_synthetic_ends(LadderFamily.RESONANCE, count=1, intervals=(INTERVAL_SEMITONES,), random_seed=0)

    ladder = synthetic_ladder(ends, weights=WEIGHTS, recipe=recipe)

    assert ladder.family is LadderFamily.RESONANCE
    assert not ladder.is_translation
    assert not np.array_equal(ladder.truth[0], ladder.truth[-1])
