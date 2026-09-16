from __future__ import annotations

from typing import Final

import numpy as np
import pytest
from numpy.typing import NDArray

from samplemorph.partials.correspondence.shifts import agreed_shifts, no_shifts
from samplemorph.partials.places import PartialPlaces
from samplemorph.partials.profile import Correspondence
from samplemorph.partials.tracks import CENTS_PER_OCTAVE

SPREAD_CENTS: Final[float] = 20.0
LARGEST_COUNT: Final[int] = 4
CENTS_TOLERANCE: Final[float] = 5.0
FIFTH_CENTS: Final[float] = 701.955


def _voices(frequencies_hz: tuple[float, ...]) -> PartialPlaces:
    count = len(frequencies_hz)
    return PartialPlaces(
        cents=CENTS_PER_OCTAVE * np.log2(np.array(frequencies_hz, dtype=np.float64)),
        share=np.full(count, 1.0 / count if count else 0.0),
        onset=np.zeros(count),
        offset=np.ones(count),
    )


def _one_to_one(count: int) -> NDArray[np.intp]:
    return np.stack((np.arange(count), np.arange(count)), axis=1).astype(np.intp)


def _shifts(
    first: tuple[float, ...],
    second: tuple[float, ...],
    *,
    lines: tuple[int, ...] | None = None,
    largest: int = LARGEST_COUNT,
):
    here, there = _voices(first), _voices(second)
    return agreed_shifts(
        here,
        there,
        matched=_one_to_one(here.count),
        lines=np.array(lines if lines is not None else range(here.count), dtype=np.intp),
        correspondence=Correspondence(largest_shift_count=largest, shift_spread_cents=SPREAD_CENTS),
    )


def test_a_series_travelling_one_interval_agrees_on_that_interval() -> None:
    shifts = _shifts((100.0, 200.0, 300.0, 400.0), (150.0, 300.0, 450.0, 600.0))

    assert shifts.count == 1
    assert shifts.cents[0] == pytest.approx(-FIFTH_CENTS, abs=CENTS_TOLERANCE)


def test_two_voices_travelling_differently_agree_on_one_interval_each() -> None:
    """A chord moving voice by voice stands on as many moves as it has voices."""
    shifts = _shifts((200.0, 400.0, 300.0, 600.0), (200.0, 400.0, 450.0, 900.0))

    assert shifts.count == 2
    assert np.allclose(np.sort(shifts.cents), (-FIFTH_CENTS, 0.0), atol=CENTS_TOLERANCE)


def test_a_line_carrying_several_pairs_travels_by_the_move_its_own_pairs_stand_on() -> None:
    shifts = _shifts((200.0, 400.0, 600.0), (300.0, 600.0, 900.0), lines=(0, 0, 0))

    assert np.allclose(shifts.by_channel, FIFTH_CENTS * -1.0, atol=CENTS_TOLERANCE)


def test_a_line_standing_on_one_pair_alone_travels_by_any_move_the_sounds_agree_on() -> None:
    shifts = _shifts((200.0, 400.0, 600.0), (300.0, 600.0, 900.0), lines=(0, 0, 1))

    assert np.isnan(shifts.by_channel[2])
    assert np.allclose(shifts.by_channel[:2], FIFTH_CENTS * -1.0, atol=CENTS_TOLERANCE)


def test_a_line_holds_the_move_most_of_what_it_carries_travels_by() -> None:
    """One pair wandering off leaves the line where the rest of it stands."""
    shifts = _shifts((200.0, 400.0, 600.0, 800.0), (300.0, 600.0, 900.0, 800.0), lines=(0, 0, 0, 0))

    assert np.allclose(shifts.by_channel, FIFTH_CENTS * -1.0, atol=CENTS_TOLERANCE)


def test_a_pairing_with_nothing_in_it_agrees_on_nothing() -> None:
    shifts = _shifts((), ())

    assert shifts.count == 0


def test_a_correspondence_asking_for_no_moves_leaves_every_channel_free() -> None:
    shifts = _shifts((200.0, 400.0), (300.0, 600.0), largest=0)

    assert shifts.count == 0
    assert np.all(np.isnan(shifts.by_channel))


def test_moves_read_before_a_pairing_stands_leave_every_channel_free() -> None:
    shifts = no_shifts(3)

    assert shifts.count == 0
    assert np.all(np.isnan(shifts.by_channel))
