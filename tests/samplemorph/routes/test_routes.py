from __future__ import annotations

from typing import Final

import numpy as np
import pytest

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.codecs.identity import IdentityCodec
from samplemorph.geometry import log_frequency_geometry
from samplemorph.morphers.linear import LinearMorpher
from samplemorph.pipeline import MorphRoute
from samplemorph.registries import CANONICALIZER_REGISTRY, DEFAULT_CANONICALIZER_NAME
from samplemorph.routes.analysis import AnalysisRoute, SpectralPath
from samplemorph.routes.kinds import pair_through
from samplemorph.routes.latent import LatentRoute
from samplemorph.routes.route import HeardMono, hear_in_frame
from samplemorph.transport.blend import blend
from samplemorph.transport.morph import transport
from samplemorph.transport.settings import TransportSettings
from samplemorph.vocoders.pghi import PghiVocoder
from tests.samplemorph.conftest import harmonic_tone

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


@pytest.mark.parametrize("path", (transport, blend))
def test_an_analysis_route_renders_each_end_at_its_own_length_and_the_middle_between(
    path: SpectralPath, ends: tuple[HeardMono, HeardMono]
) -> None:
    route = AnalysisRoute(path=path, geometry=log_frequency_geometry(), settings=TransportSettings())
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
