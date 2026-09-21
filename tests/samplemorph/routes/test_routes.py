from __future__ import annotations

from typing import Final

import numpy as np
import pytest

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.coordinates.readers import subharmonic_reader
from samplemorph.envelope.morph import EnvelopePath
from samplemorph.envelope.settings import EnvelopeSettings
from samplemorph.geometry import log_frequency_geometry
from samplemorph.routes.envelope import EnvelopeRoute
from samplemorph.routes.route import HeardMono, hear_in_frame
from samplemorph.transport.settings import TransportSettings
from tests.samplemorph.conftest import harmonic_tone, noise_burst

SHORT_FRAME_COUNT: Final[int] = 4096
LONG_FRAME_COUNT: Final[int] = 16384
MIDPOINT: Final[float] = 0.5


@pytest.fixture(scope="module")
def ends() -> tuple[HeardMono, HeardMono]:
    return (
        hear_in_frame(
            harmonic_tone(SHORT_FRAME_COUNT, frequency=220.0), rate_hz=NOMINAL_WAV_RATE, target_rate_hz=NOMINAL_WAV_RATE
        ),
        hear_in_frame(
            harmonic_tone(LONG_FRAME_COUNT, frequency=330.0), rate_hz=NOMINAL_WAV_RATE, target_rate_hz=NOMINAL_WAV_RATE
        ),
    )


def test_frames_heard_at_half_the_frames_rate_last_twice_as_many_frames() -> None:
    heard = hear_in_frame(
        harmonic_tone(SHORT_FRAME_COUNT, frequency=220.0),
        rate_hz=NOMINAL_WAV_RATE / 2.0,
        target_rate_hz=NOMINAL_WAV_RATE,
    )

    assert heard.mono.ndim == 1
    assert heard.mono.shape[0] == 2 * SHORT_FRAME_COUNT
    assert heard.rate_hz == NOMINAL_WAV_RATE


def _route(*, glide: bool) -> EnvelopeRoute:
    return EnvelopeRoute(
        path=EnvelopePath(envelope_settings=EnvelopeSettings()),
        reader=subharmonic_reader() if glide else None,
        geometry=log_frequency_geometry(),
        settings=TransportSettings(),
    )


@pytest.mark.parametrize("glide", (False, True), ids=("holding every pitch", "gliding"))
def test_the_route_renders_each_end_at_its_own_length_and_the_middle_between(
    glide: bool, ends: tuple[HeardMono, HeardMono]
) -> None:
    prepared = _route(glide=glide).prepare_pair(*ends)

    lengths = [prepared.render(weight=weight).shape[0] for weight in (0.0, MIDPOINT, 1.0)]

    assert lengths == [SHORT_FRAME_COUNT, int(np.sqrt(SHORT_FRAME_COUNT * LONG_FRAME_COUNT)), LONG_FRAME_COUNT]


def test_a_gliding_route_with_an_end_of_no_trusted_pitch_renders_as_the_route_that_holds_pitch(
    ends: tuple[HeardMono, HeardMono],
) -> None:
    burst = hear_in_frame(
        noise_burst(LONG_FRAME_COUNT, seed=3), rate_hz=NOMINAL_WAV_RATE, target_rate_hz=NOMINAL_WAV_RATE
    )
    gliding, held = _route(glide=True), _route(glide=False)

    assert gliding.prepare(burst).pitch_semitones is None
    assert gliding.prepare(ends[0]).pitch_semitones is not None
    assert np.array_equal(
        gliding.prepare_pair(ends[0], burst).render(weight=MIDPOINT),
        held.prepare_pair(ends[0], burst).render(weight=MIDPOINT),
    )
