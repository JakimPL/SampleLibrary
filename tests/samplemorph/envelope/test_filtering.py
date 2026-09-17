from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pytest
from numpy.typing import NDArray

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.canonicalizers.common import PreparedMono, analysis_transform, prepare_mono
from samplemorph.envelope.filtering import filter_gain, filtered_waveform, response_gain
from samplemorph.envelope.morph import EnvelopePath
from samplemorph.envelope.response import EnvelopeResponse, HeldEnd, ResponseReading, build_envelope_response
from samplemorph.envelope.settings import EnvelopeSettings
from samplemorph.transport.analysis import TransportAnalysis, analyze
from samplemorph.transport.settings import TransportSettings
from tests.samplemorph.transport.conftest import CLIP_FRAMES, GEOMETRY, tone

LOW_HZ: Final[float] = 300.0
HIGH_HZ: Final[float] = 450.0
LONG_CLIP_FRAMES: Final[int] = CLIP_FRAMES * 2
SETTINGS: Final[EnvelopeSettings] = EnvelopeSettings()
READING: Final[ResponseReading] = ResponseReading(
    geometry=GEOMETRY, settings=TransportSettings(), envelope_settings=SETTINGS
)
PATH_WEIGHTS: Final[tuple[float, ...]] = (0.0, 0.25, 0.5, 0.75, 1.0)
MAGNITUDE_TOLERANCE: Final[float] = 1e-5
SOUND_TOLERANCE: Final[float] = 1e-10
UNIT_GAIN_TOLERANCE: Final[float] = 1e-6
HELD_ENDS: Final[tuple[float, ...]] = (0.0, 1.0)


@dataclass(frozen=True)
class HeardSound:
    """One sound of a pair as every reading of it: the frames, the analysis, and the transform they share."""

    mono: PreparedMono
    analysis: TransportAnalysis
    transform: NDArray[np.complex128]


@dataclass(frozen=True)
class HeardPair:
    """Two sounds read together, beside the response measured between them."""

    first: HeardSound
    second: HeardSound
    response: EnvelopeResponse

    def held(self, end: HeldEnd) -> HeardSound:
        return self.first if end is HeldEnd.FIRST else self.second


def _heard(mono: NDArray[np.float64]) -> HeardSound:
    prepared = prepare_mono(mono)
    return HeardSound(
        mono=prepared,
        analysis=analyze(prepared, rate_hz=NOMINAL_WAV_RATE, geometry=GEOMETRY, settings=TransportSettings()),
        transform=analysis_transform(prepared, geometry=GEOMETRY),
    )


@pytest.fixture(scope="module")
def pair() -> HeardPair:
    first = _heard(tone(LOW_HZ))
    second = _heard(tone(HIGH_HZ, frame_count=LONG_CLIP_FRAMES))
    return HeardPair(
        first=first,
        second=second,
        response=build_envelope_response(
            first.analysis,
            second.analysis,
            rate_hz=NOMINAL_WAV_RATE,
            reading=READING,
        ),
    )


@pytest.mark.parametrize("held", tuple(HeldEnd), ids=("the first sound held", "the second sound held"))
@pytest.mark.parametrize("weight", PATH_WEIGHTS, ids=tuple(f"at weight {weight}" for weight in PATH_WEIGHTS))
def test_a_filter_draws_the_magnitude_the_route_renders(pair: HeardPair, held: HeldEnd, weight: float) -> None:
    settings = EnvelopeSettings(timeline=held.timeline, excitation=held.excitation)
    path = EnvelopePath(envelope_settings=settings)
    rendered = path(
        pair.first.analysis, pair.second.analysis, weight=weight, geometry=GEOMETRY, settings=TransportSettings()
    ).magnitude

    filtered = np.abs(pair.held(held).transform) * response_gain(pair.response, held=held, weight=weight)

    assert np.abs(filtered - rendered).max() / rendered.max() < MAGNITUDE_TOLERANCE


@pytest.mark.parametrize(
    ("held", "weight"),
    ((HeldEnd.FIRST, 0.0), (HeldEnd.SECOND, 1.0)),
    ids=("the first sound at its own end", "the second sound at its own end"),
)
def test_the_end_a_filter_holds_sounds_as_that_sound_itself(pair: HeardPair, held: HeldEnd, weight: float) -> None:
    sound = pair.held(held)

    waveform = filtered_waveform(sound.transform, pair.response.filter_held_to(held), weight=weight, geometry=GEOMETRY)

    np.testing.assert_allclose(waveform, sound.mono, atol=SOUND_TOLERANCE)


@pytest.mark.parametrize(
    ("held", "weight"),
    ((HeldEnd.FIRST, 0.0), (HeldEnd.SECOND, 1.0)),
    ids=("the first sound at its own end", "the second sound at its own end"),
)
def test_the_gain_at_the_end_a_filter_holds_is_one_throughout(pair: HeardPair, held: HeldEnd, weight: float) -> None:
    gain = response_gain(pair.response, held=held, weight=weight)

    assert np.abs(gain - 1.0).max() < UNIT_GAIN_TOLERANCE


@pytest.mark.parametrize("held", tuple(HeldEnd), ids=("the first sound held", "the second sound held"))
def test_every_point_of_a_held_path_lasts_as_long_as_the_sound_it_holds(pair: HeardPair, held: HeldEnd) -> None:
    sound = pair.held(held)
    envelope_filter = pair.response.filter_held_to(held)

    lengths = {
        len(filtered_waveform(sound.transform, envelope_filter, weight=weight, geometry=GEOMETRY))
        for weight in PATH_WEIGHTS
    }

    assert lengths == {sound.analysis.sample_count}


def test_a_gain_reads_one_row_per_bin_of_the_reading_it_came_from(pair: HeardPair) -> None:
    envelope_filter = pair.response.first

    gain = filter_gain(envelope_filter, weight=0.5, bin_count=pair.response.description.bin_count)

    assert gain.shape == (pair.response.description.bin_count, envelope_filter.description.frame_count)
