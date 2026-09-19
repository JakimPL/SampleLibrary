from __future__ import annotations

from typing import Final

import pytest

from samplemorph.canonicalizers.common import PreparedMono, prepare_mono
from samplemorph.descriptors.pooling import pooled_band_count
from samplemorph.geometry import LogFrequencyGeometry, log_frequency_geometry
from samplemorph.measurement.ladders.axis import PooledAxis
from samplemorph.measurement.ladders.truth import Ladder, LadderRecipe, ladder_weights, retuned_ladder
from samplemorph.registries import canonicalizer_for_geometry
from samplemorph.tones import HarmonicTone, harmonic_tone

GEOMETRY: Final[LogFrequencyGeometry] = log_frequency_geometry()
AXIS: Final[PooledAxis] = PooledAxis(
    geometry=GEOMETRY, band_count=pooled_band_count(GEOMETRY, bands_per_semitone=1), bands_per_semitone=1
)
WEIGHTS: Final[tuple[float, ...]] = ladder_weights(9)
TONE: Final[HarmonicTone] = HarmonicTone(fundamental_hz=220.0, resonance_hz=1500.0)
INTERVAL_SEMITONES: Final[float] = 5.0


@pytest.fixture(scope="session")
def recipe() -> LadderRecipe:
    return LadderRecipe(canonicalizer=canonicalizer_for_geometry(GEOMETRY), axis=AXIS)


@pytest.fixture(scope="session")
def tone_mono() -> PreparedMono:
    return prepare_mono(harmonic_tone(TONE, rate_hz=float(GEOMETRY.analysis_rate_hz)))


@pytest.fixture(scope="session")
def retuned(tone_mono: PreparedMono, recipe: LadderRecipe) -> Ladder:
    """A resonant tone read at rates spanning five semitones."""
    return retuned_ladder(tone_mono, name="tone", interval_semitones=INTERVAL_SEMITONES, weights=WEIGHTS, recipe=recipe)
