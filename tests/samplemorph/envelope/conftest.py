from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pytest
from numpy.typing import NDArray

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.canonicalizers.common import PreparedMono, analysis_transform, prepare_mono
from samplemorph.envelope.response import EnvelopeResponse, HeldEnd, ResponseReading, build_envelope_response
from samplemorph.envelope.settings import EnvelopeSettings
from samplemorph.transport.analysis import TransportAnalysis, analyze
from samplemorph.transport.settings import TransportSettings
from tests.samplemorph.transport.conftest import CLIP_FRAMES, GEOMETRY, tone

PAIR_LOW_HZ: Final[float] = 300.0
PAIR_HIGH_HZ: Final[float] = 450.0
LONG_CLIP_FRAMES: Final[int] = CLIP_FRAMES * 2
ENVELOPE_SETTINGS: Final[EnvelopeSettings] = EnvelopeSettings()
READING: Final[ResponseReading] = ResponseReading(
    geometry=GEOMETRY, settings=TransportSettings(), envelope_settings=ENVELOPE_SETTINGS
)


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
        match end:
            case HeldEnd.FIRST:
                return self.first
            case HeldEnd.SECOND:
                return self.second


def heard(mono: NDArray[np.float64]) -> HeardSound:
    """One sound read through the analysis every response is measured against."""
    prepared = prepare_mono(mono)
    return HeardSound(
        mono=prepared,
        analysis=analyze(prepared, rate_hz=NOMINAL_WAV_RATE, geometry=GEOMETRY),
        transform=analysis_transform(prepared, geometry=GEOMETRY),
    )


@pytest.fixture(scope="package")
def pair() -> HeardPair:
    first = heard(tone(PAIR_LOW_HZ))
    second = heard(tone(PAIR_HIGH_HZ, frame_count=LONG_CLIP_FRAMES))
    return HeardPair(
        first=first,
        second=second,
        response=build_envelope_response(first.analysis, second.analysis, rate_hz=NOMINAL_WAV_RATE, reading=READING),
    )
