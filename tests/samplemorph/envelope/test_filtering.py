from __future__ import annotations

from typing import Final

import numpy as np
import pytest

from samplemorph.envelope.filtering import filter_gain, filtered_waveform, response_gain
from samplemorph.envelope.morph import EnvelopePath
from samplemorph.envelope.response import HeldEnd
from samplemorph.envelope.settings import EnvelopeSettings
from tests.samplemorph.envelope.conftest import GEOMETRY, READING, HeardPair

PATH_WEIGHTS: Final[tuple[float, ...]] = (0.0, 0.25, 0.5, 0.75, 1.0)
MAGNITUDE_TOLERANCE: Final[float] = 1e-5
SOUND_TOLERANCE: Final[float] = 1e-10
UNIT_GAIN_TOLERANCE: Final[float] = 1e-6


@pytest.mark.parametrize("held", tuple(HeldEnd), ids=("the first sound held", "the second sound held"))
@pytest.mark.parametrize("weight", PATH_WEIGHTS, ids=tuple(f"at weight {weight}" for weight in PATH_WEIGHTS))
def test_a_filter_draws_the_magnitude_the_route_renders(pair: HeardPair, held: HeldEnd, weight: float) -> None:
    settings = EnvelopeSettings(timeline=held.timeline, excitation=held.excitation)
    path = EnvelopePath(envelope_settings=settings)
    rendered = path(
        pair.first.analysis, pair.second.analysis, weight=weight, geometry=GEOMETRY, settings=READING.settings
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
