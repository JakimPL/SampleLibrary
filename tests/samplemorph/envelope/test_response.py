from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pytest

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.envelope.response import HeldEnd
from samplemorph.geometry import fourier_bin_count
from tests.samplemorph.envelope.conftest import ENVELOPE_SETTINGS, READING, HeardPair

FIRST_END: Final[float] = 0.0
SECOND_END: Final[float] = 1.0
OFF_THE_PATH: Final[tuple[float, ...]] = (-0.1, 1.1)


@dataclass(frozen=True)
class TravelCase:
    """How far a filter's sound stands from its own envelope at one end of the path."""

    held: HeldEnd
    weight: float
    travel: float


def test_a_response_describes_the_reading_its_coefficients_came_from(pair: HeardPair) -> None:
    description = pair.response.description

    assert description.fft_length == READING.geometry.fft_length
    assert description.hop_length == READING.geometry.hop_length
    assert description.bin_count == fourier_bin_count(fft_length=READING.geometry.fft_length)
    assert description.rate_hz == NOMINAL_WAV_RATE
    assert description.coefficient_count == ENVELOPE_SETTINGS.coefficient_count
    assert description.floor_db == ENVELOPE_SETTINGS.floor_db


@pytest.mark.parametrize("held", tuple(HeldEnd), ids=("the first sound held", "the second sound held"))
def test_each_filter_lasts_as_long_as_the_sound_it_holds(pair: HeardPair, held: HeldEnd) -> None:
    envelope_filter = pair.response.filter_held_to(held)

    assert envelope_filter.description.sample_count == pair.held(held).analysis.sample_count
    assert envelope_filter.held is held


@pytest.mark.parametrize("held", tuple(HeldEnd), ids=("the first sound held", "the second sound held"))
def test_a_filter_holds_one_set_of_coefficients_per_frame_it_covers(pair: HeardPair, held: HeldEnd) -> None:
    envelope_filter = pair.response.filter_held_to(held)

    assert envelope_filter.coefficients.shape == (
        pair.response.description.coefficient_count,
        envelope_filter.description.frame_count,
    )


@pytest.mark.parametrize(
    "case",
    (
        TravelCase(HeldEnd.FIRST, FIRST_END, 0.0),
        TravelCase(HeldEnd.FIRST, SECOND_END, 1.0),
        TravelCase(HeldEnd.SECOND, SECOND_END, 0.0),
        TravelCase(HeldEnd.SECOND, FIRST_END, 1.0),
    ),
    ids=(
        "the first sound at its own end",
        "the first sound at the far end",
        "the second sound at its own end",
        "the second sound at the far end",
    ),
)
def test_a_filter_stands_still_at_its_own_end_and_travels_to_the_other(pair: HeardPair, case: TravelCase) -> None:
    assert pair.response.filter_held_to(case.held).travel_at(case.weight) == pytest.approx(case.travel)


@pytest.mark.parametrize("weight", OFF_THE_PATH, ids=("under the first end", "past the second end"))
def test_a_weight_off_the_path_is_refused(pair: HeardPair, weight: float) -> None:
    with pytest.raises(ValueError, match="between weights 0 and 1"):
        pair.response.first.travel_at(weight)
