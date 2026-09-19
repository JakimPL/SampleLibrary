from __future__ import annotations

from typing import Final

import numpy as np
import pytest

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.codecs.identity import IdentityCodec
from samplemorph.coordinates.readers import subharmonic_reader
from samplemorph.envelope.morph import EnvelopePath
from samplemorph.envelope.settings import EnvelopeSettings
from samplemorph.geometry import log_frequency_geometry
from samplemorph.morphers.linear import LinearMorpher
from samplemorph.partials.morph import PartialMorph
from samplemorph.partials.presets import PROFILE_PRESETS
from samplemorph.partials.settings import PartialSettings
from samplemorph.pipeline import MorphRoute
from samplemorph.registries import CANONICALIZER_REGISTRY, DEFAULT_CANONICALIZER_NAME
from samplemorph.routes.analysis import AnalysisRoute, SpectralPath
from samplemorph.routes.gliding import GlidingRoute
from samplemorph.routes.kinds import pair_through
from samplemorph.routes.latent import LatentRoute
from samplemorph.routes.partials import PartialRoute
from samplemorph.routes.route import HeardMono, hear_in_frame
from samplemorph.transport.blend import blend
from samplemorph.transport.morph import transport
from samplemorph.transport.settings import TransportSettings
from samplemorph.vocoders.pghi import PghiVocoder
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


@pytest.mark.parametrize(
    "path",
    (transport, blend, EnvelopePath(envelope_settings=EnvelopeSettings())),
    ids=("transport", "blend", "envelope"),
)
def test_an_analysis_route_renders_each_end_at_its_own_length_and_the_middle_between(
    path: SpectralPath, ends: tuple[HeardMono, HeardMono]
) -> None:
    route = AnalysisRoute(path=path, geometry=log_frequency_geometry(), settings=TransportSettings())
    prepared = pair_through(route, *ends)

    lengths = [prepared.render(weight=weight).shape[0] for weight in (0.0, MIDPOINT, 1.0)]

    assert lengths == [SHORT_FRAME_COUNT, int(np.sqrt(SHORT_FRAME_COUNT * LONG_FRAME_COUNT)), LONG_FRAME_COUNT]


def _gliding_route() -> GlidingRoute:
    return GlidingRoute(
        path=EnvelopePath(envelope_settings=EnvelopeSettings()),
        reader=subharmonic_reader(),
        geometry=log_frequency_geometry(),
        settings=TransportSettings(),
    )


def test_a_gliding_route_renders_each_end_at_its_own_length_and_the_middle_between(
    ends: tuple[HeardMono, HeardMono],
) -> None:
    prepared = pair_through(_gliding_route(), *ends)

    lengths = [prepared.render(weight=weight).shape[0] for weight in (0.0, MIDPOINT, 1.0)]

    assert lengths == [SHORT_FRAME_COUNT, int(np.sqrt(SHORT_FRAME_COUNT * LONG_FRAME_COUNT)), LONG_FRAME_COUNT]


def test_a_gliding_route_with_an_end_of_no_trusted_pitch_renders_as_the_envelope_route(
    ends: tuple[HeardMono, HeardMono],
) -> None:
    burst = hear_in_frame(
        noise_burst(LONG_FRAME_COUNT, seed=3), rate_hz=NOMINAL_WAV_RATE, target_rate_hz=NOMINAL_WAV_RATE
    )
    gliding = _gliding_route()
    held = AnalysisRoute(path=gliding.path, geometry=gliding.geometry, settings=gliding.settings)

    prepared = gliding.prepare(burst)

    assert prepared.pitch_semitones is None
    assert gliding.prepare(ends[0]).pitch_semitones is not None
    assert np.array_equal(
        pair_through(gliding, ends[0], burst).render(weight=MIDPOINT),
        pair_through(held, ends[0], burst).render(weight=MIDPOINT),
    )


def test_the_partials_route_renders_each_end_at_its_own_length_and_the_middle_between(
    ends: tuple[HeardMono, HeardMono],
) -> None:
    route = PartialRoute(
        morph=PartialMorph(
            profile=PROFILE_PRESETS["slide"], geometry=log_frequency_geometry(), settings=TransportSettings()
        ),
        partial_settings=PartialSettings(),
    )
    prepared = pair_through(route, *ends)

    lengths = [prepared.render(weight=weight).shape[0] for weight in (0.0, MIDPOINT, 1.0)]

    assert lengths == [SHORT_FRAME_COUNT, int(np.sqrt(SHORT_FRAME_COUNT * LONG_FRAME_COUNT)), LONG_FRAME_COUNT]


def test_the_latent_route_renders_between_two_ends_through_its_codec(ends: tuple[HeardMono, HeardMono]) -> None:
    canonicalizer = CANONICALIZER_REGISTRY[DEFAULT_CANONICALIZER_NAME]()
    route = LatentRoute(
        MorphRoute(
            canonicalizer=canonicalizer,
            codec=IdentityCodec(canonicalizer.geometry),
            vocoder=PghiVocoder(),
            morpher=LinearMorpher(),
        )
    )

    rendered = pair_through(route, *ends).render(weight=MIDPOINT)

    assert rendered.shape[0] > 0
    assert np.all(np.isfinite(rendered))
