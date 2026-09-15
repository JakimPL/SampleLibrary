from __future__ import annotations

import numpy as np
import pytest

from samplemorph.transport.blend import blend
from samplemorph.transport.settings import TransportSettings
from tests.samplemorph.transport.conftest import BIN_SPACING_HZ, GEOMETRY, analysis_of, middle_spectrum, sines

LOBE_REACH_BINS = 2
BOTH_ENDS_WITHIN_DB = 12.0
BETWEEN_UNDER_DB = 20.0


def _blend(weight: float) -> np.ndarray:
    first = analysis_of(sines((300.0,)))
    second = analysis_of(sines((600.0,)))
    return blend(
        first,
        second,
        weight=weight,
        geometry=GEOMETRY,
        settings=TransportSettings(),
    ).magnitude


def _level_near(spectrum: np.ndarray, frequency_hz: float) -> float:
    """The loudest bin within reach of a frequency, in decibels under the whole spectrum's peak."""
    center = int(round(frequency_hz / BIN_SPACING_HZ))
    nearby = spectrum[center - LOBE_REACH_BINS : center + LOBE_REACH_BINS + 1]
    return float(10.0 * np.log10(nearby.max() / spectrum.max()))


def test_the_crossfade_holds_both_ends_in_place_at_its_midpoint() -> None:
    spectrum = middle_spectrum(_blend(0.5))

    assert _level_near(spectrum, 300.0) > -BOTH_ENDS_WITHIN_DB
    assert _level_near(spectrum, 600.0) > -BOTH_ENDS_WITHIN_DB
    assert _level_near(spectrum, float(np.sqrt(300.0 * 600.0))) < -BETWEEN_UNDER_DB


def test_the_crossfade_returns_each_end_at_its_own_weight() -> None:
    first = analysis_of(sines((300.0,)))

    assert np.array_equal(_blend(0.0), np.sqrt(first.energy))


def test_a_crossfade_outside_its_weights_is_refused() -> None:
    with pytest.raises(ValueError, match="between weights 0 and 1"):
        _blend(1.5)
