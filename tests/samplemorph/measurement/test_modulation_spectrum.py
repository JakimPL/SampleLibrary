from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest
from scipy.signal import hilbert

from samplecore.auditory.modulation import ModulationAxis
from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.measurement.modulation_spectrum import (
    ModulationLobeDepths,
    ModulationSpectrumDistance,
    modulation_lobe_depths,
    modulation_spectrum_distance,
)

LOW_HEARD_RATE_HZ = 8363
TONE_SECONDS = 1.0
CARRIER_HZ = 3000.0
FUNDAMENTAL_HZ = 440.0
MODULATION_DEPTH = 0.5
QUIET_PARTIAL_WEIGHT = 0.1
SHORT_CLIP_SECONDS = 0.15
INVARIANCE_SHARE = 0.05


@dataclass(frozen=True)
class LobeCase:
    modulation_hz: float
    sample_rate_hz: int
    dominant: ModulationAxis
    other: ModulationAxis


LOBE_CASES = (
    LobeCase(6.0, NOMINAL_WAV_RATE, dominant=ModulationAxis.FLUCTUATION, other=ModulationAxis.ROUGHNESS),
    LobeCase(70.0, NOMINAL_WAV_RATE, dominant=ModulationAxis.ROUGHNESS, other=ModulationAxis.FLUCTUATION),
    LobeCase(6.0, LOW_HEARD_RATE_HZ, dominant=ModulationAxis.FLUCTUATION, other=ModulationAxis.ROUGHNESS),
)


def _times(sample_rate_hz: int, seconds: float = TONE_SECONDS) -> np.ndarray:
    return np.arange(int(seconds * sample_rate_hz)) / sample_rate_hz


def _carrier(sample_rate_hz: int) -> np.ndarray:
    return np.cos(2.0 * np.pi * CARRIER_HZ * _times(sample_rate_hz))


def _modulated(modulation_hz: float, *, sample_rate_hz: int) -> np.ndarray:
    return _carrier(sample_rate_hz) * (
        1.0 + MODULATION_DEPTH * np.sin(2.0 * np.pi * modulation_hz * _times(sample_rate_hz))
    )


def _depth(depths: ModulationLobeDepths, axis: ModulationAxis) -> float:
    match axis:
        case ModulationAxis.FLUCTUATION:
            return depths.fluctuation
        case ModulationAxis.ROUGHNESS:
            return depths.roughness


def _excess(reading: ModulationSpectrumDistance, axis: ModulationAxis) -> float:
    match axis:
        case ModulationAxis.FLUCTUATION:
            return reading.fluctuation_excess
        case ModulationAxis.ROUGHNESS:
            return reading.roughness_excess


@pytest.mark.parametrize("case", LOBE_CASES)
def test_added_modulation_reads_positive_on_the_lobe_that_hears_it(case: LobeCase) -> None:
    reading = modulation_spectrum_distance(
        _modulated(case.modulation_hz, sample_rate_hz=case.sample_rate_hz),
        _carrier(case.sample_rate_hz),
        source_rate_hz=case.sample_rate_hz,
    )

    assert _excess(reading, case.dominant) > 0.0
    assert _excess(reading, case.dominant) > abs(_excess(reading, case.other))
    assert reading.distance >= abs(_excess(reading, case.dominant))


def test_a_reconstruction_identical_to_its_reference_reads_zero_on_every_axis() -> None:
    reading = modulation_spectrum_distance(_carrier(NOMINAL_WAV_RATE), _carrier(NOMINAL_WAV_RATE))

    assert reading.fluctuation_excess == 0.0
    assert reading.roughness_excess == 0.0
    assert reading.distance == 0.0


def test_a_reconstruction_smoother_than_a_fluttering_reference_reads_erased_modulation() -> None:
    reading = modulation_spectrum_distance(_carrier(NOMINAL_WAV_RATE), _modulated(6.0, sample_rate_hz=NOMINAL_WAV_RATE))

    assert reading.fluctuation_excess < 0.0
    assert reading.distance > 0.0
    assert reading.distance >= abs(reading.fluctuation_excess)


@pytest.mark.parametrize("shift", ["quarter_cycle", "one_sample"])
def test_a_global_phase_shift_reads_as_no_deviation(shift: str) -> None:
    reference = _carrier(NOMINAL_WAV_RATE)
    shifted = np.imag(hilbert(reference)) if shift == "quarter_cycle" else np.roll(reference, 1)
    audible = modulation_spectrum_distance(_modulated(6.0, sample_rate_hz=NOMINAL_WAV_RATE), reference)

    reading = modulation_spectrum_distance(shifted, reference)

    assert reading.distance < INVARIANCE_SHARE * audible.distance


def test_flutter_on_a_loud_partial_counts_more_than_the_same_flutter_on_a_quiet_one() -> None:
    times = _times(NOMINAL_WAV_RATE)
    loud = np.sin(2.0 * np.pi * FUNDAMENTAL_HZ * times)
    quiet = QUIET_PARTIAL_WEIGHT * np.sin(2.0 * np.pi * 2.0 * FUNDAMENTAL_HZ * times)
    flutter = 1.0 + MODULATION_DEPTH * np.sin(2.0 * np.pi * 6.0 * times)
    reference = loud + quiet

    on_loud = modulation_spectrum_distance(loud * flutter + quiet, reference)
    on_quiet = modulation_spectrum_distance(loud + quiet * flutter, reference)

    assert on_loud.fluctuation_excess > on_quiet.fluctuation_excess > 0.0


def test_a_clip_shorter_than_a_lobe_window_is_read_whole() -> None:
    short = int(SHORT_CLIP_SECONDS * NOMINAL_WAV_RATE)

    reading = modulation_spectrum_distance(
        _modulated(6.0, sample_rate_hz=NOMINAL_WAV_RATE)[:short], _carrier(NOMINAL_WAV_RATE)[:short]
    )

    assert np.isfinite([reading.fluctuation_excess, reading.roughness_excess, reading.distance]).all()
    assert reading.distance > 0.0


@pytest.mark.parametrize("case", LOBE_CASES)
def test_a_sound_on_its_own_reads_its_modulation_on_the_lobe_that_hears_it(case: LobeCase) -> None:
    modulated = modulation_lobe_depths(
        _modulated(case.modulation_hz, sample_rate_hz=case.sample_rate_hz), source_rate_hz=case.sample_rate_hz
    )
    steady = modulation_lobe_depths(_carrier(case.sample_rate_hz), source_rate_hz=case.sample_rate_hz)

    assert _depth(modulated, case.dominant) - _depth(steady, case.dominant) > abs(
        _depth(modulated, case.other) - _depth(steady, case.other)
    )


def test_depths_read_alone_differ_by_what_a_reading_against_the_reference_adds() -> None:
    modulated = _modulated(6.0, sample_rate_hz=NOMINAL_WAV_RATE)
    carrier = _carrier(NOMINAL_WAV_RATE)

    against = modulation_spectrum_distance(modulated, carrier)
    difference = modulation_lobe_depths(modulated).fluctuation - modulation_lobe_depths(carrier).fluctuation

    assert difference == pytest.approx(against.fluctuation_excess, rel=0.25)
