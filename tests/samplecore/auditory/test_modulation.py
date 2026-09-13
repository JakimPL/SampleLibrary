from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from samplecore.auditory.envelope import COMPRESSION_EXPONENT
from samplecore.auditory.modulation import (
    MODULATION_DEPTH_FLOOR,
    ModulationAxis,
    ModulationSpectrum,
    design_modulation_front_end,
    modulation_spectra,
)

CONTAINER_RATE_HZ = 44100
LOW_HEARD_RATE_HZ = 8363
TONE_SECONDS = 1.0
CARRIER_HZ = 3000.0
AUDIBLE_DEPTH = 0.5
INAUDIBLE_DEPTH = MODULATION_DEPTH_FLOOR / 4.0
SHORT_CLIP_SAMPLES = 400


@dataclass(frozen=True)
class LobeCase:
    modulation_hz: float
    sample_rate_hz: int
    expected_axis: ModulationAxis


LOBE_CASES = (
    LobeCase(modulation_hz=6.0, sample_rate_hz=CONTAINER_RATE_HZ, expected_axis=ModulationAxis.FLUCTUATION),
    LobeCase(modulation_hz=70.0, sample_rate_hz=CONTAINER_RATE_HZ, expected_axis=ModulationAxis.ROUGHNESS),
    LobeCase(modulation_hz=6.0, sample_rate_hz=LOW_HEARD_RATE_HZ, expected_axis=ModulationAxis.FLUCTUATION),
    LobeCase(modulation_hz=70.0, sample_rate_hz=LOW_HEARD_RATE_HZ, expected_axis=ModulationAxis.ROUGHNESS),
)


def _modulated(modulation_hz: float, *, depth: float, sample_rate_hz: int) -> np.ndarray:
    times = np.arange(int(TONE_SECONDS * sample_rate_hz)) / sample_rate_hz
    carrier = np.cos(2.0 * np.pi * CARRIER_HZ * times)
    return carrier * (1.0 + depth * np.sin(2.0 * np.pi * modulation_hz * times))


def _reading(spectrum: ModulationSpectrum, *, floor: float) -> float:
    """The lobe's depth, each channel and frame counting by how far its level sits above the floor."""
    weight = np.maximum(spectrum.level - floor, 0.0)
    return float((spectrum.lobe_depth * weight).sum() / weight.sum())


def _readings(waveform: np.ndarray, *, sample_rate_hz: int) -> dict[ModulationAxis, float]:
    front_end = design_modulation_front_end(sample_rate_hz=sample_rate_hz)
    return {
        spectrum.lobe.axis: _reading(spectrum, floor=front_end.compressed_floor)
        for spectrum in modulation_spectra(waveform, front_end=front_end)
    }


@pytest.mark.parametrize("case", LOBE_CASES)
def test_a_modulation_lands_in_the_lobe_that_hears_it(case: LobeCase) -> None:
    readings = _readings(
        _modulated(case.modulation_hz, depth=AUDIBLE_DEPTH, sample_rate_hz=case.sample_rate_hz),
        sample_rate_hz=case.sample_rate_hz,
    )

    other_axes = [axis for axis in ModulationAxis if axis is not case.expected_axis]
    assert readings[case.expected_axis] > 0.0
    assert all(readings[case.expected_axis] > readings[axis] for axis in other_axes)


def test_a_steady_tone_reads_under_the_detection_floor_in_either_lobe() -> None:
    floor = design_modulation_front_end(sample_rate_hz=CONTAINER_RATE_HZ).depth_floor
    readings = _readings(_modulated(6.0, depth=0.0, sample_rate_hz=CONTAINER_RATE_HZ), sample_rate_hz=CONTAINER_RATE_HZ)

    assert all(reading < floor for reading in readings.values())


def test_the_detection_floor_separates_an_inaudible_modulation_from_an_audible_one() -> None:
    floor = design_modulation_front_end(sample_rate_hz=CONTAINER_RATE_HZ).depth_floor
    inaudible = _readings(
        _modulated(6.0, depth=INAUDIBLE_DEPTH, sample_rate_hz=CONTAINER_RATE_HZ), sample_rate_hz=CONTAINER_RATE_HZ
    )
    audible = _readings(
        _modulated(6.0, depth=AUDIBLE_DEPTH, sample_rate_hz=CONTAINER_RATE_HZ), sample_rate_hz=CONTAINER_RATE_HZ
    )

    assert inaudible[ModulationAxis.FLUCTUATION] < floor
    assert audible[ModulationAxis.FLUCTUATION] > floor


def test_a_sinusoidal_modulation_at_the_lobe_peak_reads_its_own_compressed_depth() -> None:
    front_end = design_modulation_front_end(sample_rate_hz=CONTAINER_RATE_HZ)
    readings = _readings(
        _modulated(front_end.lobes[0].peak_hz, depth=AUDIBLE_DEPTH, sample_rate_hz=CONTAINER_RATE_HZ),
        sample_rate_hz=CONTAINER_RATE_HZ,
    )

    assert readings[ModulationAxis.FLUCTUATION] == pytest.approx(COMPRESSION_EXPONENT * AUDIBLE_DEPTH, rel=0.35)


def test_a_clip_shorter_than_a_lobe_window_is_read_as_one_frame() -> None:
    front_end = design_modulation_front_end(sample_rate_hz=CONTAINER_RATE_HZ)
    short = _modulated(6.0, depth=AUDIBLE_DEPTH, sample_rate_hz=CONTAINER_RATE_HZ)[:SHORT_CLIP_SAMPLES]

    spectra = modulation_spectra(short, front_end=front_end)

    assert all(spectrum.depth.shape[1] == 1 for spectrum in spectra)
    assert all(np.isfinite(spectrum.depth).all() for spectrum in spectra)


def test_a_clip_too_short_for_any_window_says_so() -> None:
    front_end = design_modulation_front_end(sample_rate_hz=CONTAINER_RATE_HZ)

    with pytest.raises(ValueError, match="envelope points"):
        modulation_spectra(np.zeros(2), front_end=front_end)
