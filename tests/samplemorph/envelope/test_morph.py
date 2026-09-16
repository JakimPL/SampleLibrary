from __future__ import annotations

from typing import Final

import numpy as np
import pytest
from numpy.typing import NDArray

from samplemorph.envelope.morph import EnvelopePath
from samplemorph.envelope.presets import KEEPS_FIRST, KEEPS_SECOND, SWITCHES_HALFWAY
from samplemorph.envelope.settings import EnvelopeSettings
from samplemorph.transport.analysis import TransportAnalysis
from samplemorph.transport.settings import TransportSettings
from tests.samplemorph.transport.conftest import (
    BIN_SPACING_HZ,
    CLIP_FRAMES,
    GEOMETRY,
    analysis_of,
    middle_spectrum,
    tone,
)

LOW_HZ: Final[float] = 300.0
HIGH_HZ: Final[float] = 450.0
LOBE_REACH_BINS: Final[int] = 2
SOUNDING_WITHIN_DB: Final[float] = 12.0
SILENT_UNDER_DB: Final[float] = 20.0
MIDPOINT: Final[float] = 0.5
BEFORE_HALFWAY: Final[float] = 0.25
AFTER_HALFWAY: Final[float] = 0.75
REGISTER_EDGE_HZ: Final[float] = 700.0
DULL_WEIGHTS: Final[tuple[float, ...]] = (1.0, 0.1, 0.01, 0.001)


@pytest.fixture(scope="module")
def low_tone() -> TransportAnalysis:
    return analysis_of(tone(LOW_HZ))


@pytest.fixture(scope="module")
def high_tone() -> TransportAnalysis:
    return analysis_of(tone(HIGH_HZ))


def _spectrum(
    first: TransportAnalysis, second: TransportAnalysis, *, weight: float, settings: EnvelopeSettings
) -> NDArray[np.float64]:
    path = EnvelopePath(envelope_settings=settings)
    return middle_spectrum(
        path(first, second, weight=weight, geometry=GEOMETRY, settings=TransportSettings()).magnitude
    )


def _level_near(spectrum: NDArray[np.float64], frequency_hz: float) -> float:
    """The loudest bin within reach of a frequency, in decibels under the whole spectrum's peak."""
    center = int(round(frequency_hz / BIN_SPACING_HZ))
    nearby = spectrum[center - LOBE_REACH_BINS : center + LOBE_REACH_BINS + 1]
    return float(10.0 * np.log10(nearby.max() / spectrum.max()))


def _upper_register_share(spectrum: NDArray[np.float64]) -> float:
    edge = int(round(REGISTER_EDGE_HZ / BIN_SPACING_HZ))
    return float(spectrum[edge:].sum() / spectrum[:edge].sum())


def test_the_ends_are_each_sound_s_own_analysis(low_tone: TransportAnalysis, high_tone: TransportAnalysis) -> None:
    path = EnvelopePath(envelope_settings=KEEPS_FIRST)

    first = path(low_tone, high_tone, weight=0.0, geometry=GEOMETRY, settings=TransportSettings())
    second = path(low_tone, high_tone, weight=1.0, geometry=GEOMETRY, settings=TransportSettings())

    assert np.array_equal(first.magnitude, np.sqrt(low_tone.energy))
    assert np.array_equal(second.magnitude, np.sqrt(high_tone.energy))


def test_the_midpoint_sounds_the_first_tone_s_harmonics_and_none_of_the_second_s(
    low_tone: TransportAnalysis, high_tone: TransportAnalysis
) -> None:
    kept = _spectrum(low_tone, high_tone, weight=MIDPOINT, settings=KEEPS_FIRST)

    assert _level_near(kept, LOW_HZ) > -SOUNDING_WITHIN_DB
    assert _level_near(kept, 2.0 * LOW_HZ) > -SOUNDING_WITHIN_DB
    assert _level_near(kept, HIGH_HZ) < -SILENT_UNDER_DB


def test_the_second_tone_s_excitation_sounds_from_the_switch_weight_on(
    low_tone: TransportAnalysis, high_tone: TransportAnalysis
) -> None:
    second_throughout = _spectrum(low_tone, high_tone, weight=MIDPOINT, settings=KEEPS_SECOND)
    before = _spectrum(low_tone, high_tone, weight=BEFORE_HALFWAY, settings=SWITCHES_HALFWAY)
    after = _spectrum(low_tone, high_tone, weight=AFTER_HALFWAY, settings=SWITCHES_HALFWAY)

    for switched in (second_throughout, after):
        assert _level_near(switched, HIGH_HZ) > -SOUNDING_WITHIN_DB
        assert _level_near(switched, LOW_HZ) < -SILENT_UNDER_DB
    assert _level_near(before, LOW_HZ) > -SOUNDING_WITHIN_DB
    assert _level_near(before, HIGH_HZ) < -SILENT_UNDER_DB


def test_the_envelope_moves_the_balance_of_registers_between_the_ends(low_tone: TransportAnalysis) -> None:
    dull = analysis_of(tone(LOW_HZ, weights=DULL_WEIGHTS))

    bright_share = _upper_register_share(middle_spectrum(np.sqrt(low_tone.energy)))
    dull_share = _upper_register_share(middle_spectrum(np.sqrt(dull.energy)))
    middle_share = _upper_register_share(_spectrum(low_tone, dull, weight=MIDPOINT, settings=KEEPS_FIRST))

    assert dull_share < middle_share < bright_share


@pytest.mark.parametrize("settings", (KEEPS_FIRST, KEEPS_SECOND), ids=("first", "second"))
def test_a_tone_meeting_silence_renders_finite(low_tone: TransportAnalysis, settings: EnvelopeSettings) -> None:
    silence = analysis_of(np.zeros(CLIP_FRAMES))
    path = EnvelopePath(envelope_settings=settings)

    magnitude = path(low_tone, silence, weight=MIDPOINT, geometry=GEOMETRY, settings=TransportSettings()).magnitude

    assert np.all(np.isfinite(magnitude))


def test_a_weight_outside_the_path_is_refused(low_tone: TransportAnalysis, high_tone: TransportAnalysis) -> None:
    with pytest.raises(ValueError, match="between weights 0 and 1"):
        EnvelopePath(envelope_settings=KEEPS_FIRST)(
            low_tone, high_tone, weight=1.5, geometry=GEOMETRY, settings=TransportSettings()
        )
