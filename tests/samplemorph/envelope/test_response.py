from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pytest

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.envelope.response import EnvelopeResponse, HeldEnd, ResponseReading, build_envelope_response
from samplemorph.envelope.settings import EnvelopeSettings
from samplemorph.geometry import fourier_bin_count
from samplemorph.transport.analysis import TransportAnalysis
from samplemorph.transport.settings import TransportSettings
from tests.samplemorph.transport.conftest import CLIP_FRAMES, GEOMETRY, analysis_of, tone

LOW_HZ: Final[float] = 300.0
HIGH_HZ: Final[float] = 450.0
LONG_CLIP_FRAMES: Final[int] = CLIP_FRAMES * 2
SETTINGS: Final[EnvelopeSettings] = EnvelopeSettings()
READING: Final[ResponseReading] = ResponseReading(
    geometry=GEOMETRY, settings=TransportSettings(), envelope_settings=SETTINGS
)
FIRST_END: Final[float] = 0.0
SECOND_END: Final[float] = 1.0
OFF_THE_PATH: Final[tuple[float, ...]] = (-0.1, 1.1)


@dataclass(frozen=True)
class TravelCase:
    """How far a filter's sound stands from its own envelope at one end of the path."""

    held: HeldEnd
    weight: float
    travel: float


@pytest.fixture(scope="module")
def short_tone() -> TransportAnalysis:
    return analysis_of(tone(LOW_HZ))


@pytest.fixture(scope="module")
def long_tone() -> TransportAnalysis:
    return analysis_of(tone(HIGH_HZ, frame_count=LONG_CLIP_FRAMES))


@pytest.fixture(scope="module")
def response(short_tone: TransportAnalysis, long_tone: TransportAnalysis) -> EnvelopeResponse:
    return build_envelope_response(
        short_tone,
        long_tone,
        rate_hz=NOMINAL_WAV_RATE,
        reading=READING,
    )


def test_a_response_describes_the_reading_its_coefficients_came_from(response: EnvelopeResponse) -> None:
    description = response.description

    assert description.fft_length == GEOMETRY.fft_length
    assert description.hop_length == GEOMETRY.hop_length
    assert description.bin_count == fourier_bin_count(fft_length=GEOMETRY.fft_length)
    assert description.rate_hz == NOMINAL_WAV_RATE
    assert description.coefficient_count == SETTINGS.coefficient_count
    assert description.floor_db == SETTINGS.floor_db


def test_each_filter_lasts_as_long_as_the_sound_it_holds(
    response: EnvelopeResponse, short_tone: TransportAnalysis, long_tone: TransportAnalysis
) -> None:
    assert response.first.description.sample_count == short_tone.sample_count
    assert response.second.description.sample_count == long_tone.sample_count


def test_a_filter_holds_one_set_of_coefficients_per_frame_it_covers(response: EnvelopeResponse) -> None:
    for envelope_filter in (response.first, response.second):
        assert envelope_filter.coefficients.shape == (
            response.description.coefficient_count,
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
def test_a_filter_stands_still_at_its_own_end_and_travels_to_the_other(
    response: EnvelopeResponse, case: TravelCase
) -> None:
    assert response.filter_held_to(case.held).travel_at(case.weight) == pytest.approx(case.travel)


@pytest.mark.parametrize("weight", OFF_THE_PATH, ids=("under the first end", "past the second end"))
def test_a_weight_off_the_path_is_refused(response: EnvelopeResponse, weight: float) -> None:
    with pytest.raises(ValueError, match="between weights 0 and 1"):
        response.first.travel_at(weight)
