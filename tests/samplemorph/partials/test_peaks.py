from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pytest

from samplemorph.partials.peaks import analysis_length
from samplemorph.partials.settings import PartialSettings
from tests.samplemorph.partials.conftest import RATE_HZ, peaks_of, times

AMPLITUDE: Final[float] = 0.5
CENTS_TOLERANCE: Final[float] = 0.5
DECIBEL_TOLERANCE: Final[float] = 0.2
CLOSE_CENTS_TOLERANCE: Final[float] = 3.0
CLOSE_BINS: Final[float] = 3.0
NOISE_PEAKS_PER_FRAME_CEILING: Final[float] = 1.0


@dataclass(frozen=True)
class LengthCase:
    rate_hz: float
    length: int


@pytest.mark.parametrize(
    "case", (LengthCase(44100.0, 4096), LengthCase(22050.0, 2048), LengthCase(11025.0, 1024), LengthCase(8363.0, 1024))
)
def test_the_analysis_lasts_about_the_same_time_as_heard_at_every_rate(case: LengthCase) -> None:
    assert analysis_length(case.rate_hz, settings=PartialSettings()) == case.length


def _middle(values: np.ndarray, frames: np.ndarray, *, frame_count: int) -> np.ndarray:
    return values[(frames > frame_count // 4) & (frames < 3 * frame_count // 4)]


@pytest.mark.parametrize("frequency_hz", (440.0, 1000.0))
def test_a_steady_sine_reads_its_own_frequency_and_amplitude(frequency_hz: float) -> None:
    peaks = peaks_of(AMPLITUDE * np.sin(2.0 * np.pi * frequency_hz * times()))

    frequencies = _middle(peaks.frequency_hz, peaks.frames, frame_count=peaks.frame_count)
    amplitudes = _middle(peaks.amplitude, peaks.frames, frame_count=peaks.frame_count)
    assert np.abs(1200.0 * np.log2(frequencies / frequency_hz)).max() <= CENTS_TOLERANCE
    assert np.abs(20.0 * np.log10(amplitudes / AMPLITUDE)).max() <= DECIBEL_TOLERANCE


def test_two_sines_three_bins_apart_each_read_their_own_frequency() -> None:
    """Each lobe's skirt swings the other's vertex by a cent or two as the pair beats, around the true frequency."""
    window_length = analysis_length(RATE_HZ, settings=PartialSettings())
    lower = 1000.0
    upper = lower + CLOSE_BINS * RATE_HZ / window_length
    peaks = peaks_of(np.sin(2.0 * np.pi * lower * times()) + np.sin(2.0 * np.pi * upper * times()))

    frequencies = _middle(peaks.frequency_hz, peaks.frames, frame_count=peaks.frame_count)
    nearest = np.where(np.abs(frequencies - lower) < np.abs(frequencies - upper), lower, upper)
    cents = 1200.0 * np.log2(frequencies / nearest)
    assert np.unique(nearest).size == 2
    for target in (lower, upper):
        assert abs(float(np.median(cents[nearest == target]))) <= CENTS_TOLERANCE
    assert np.abs(cents).max() <= CLOSE_CENTS_TOLERANCE


def test_noise_holds_almost_no_sinusoid() -> None:
    peaks = peaks_of(np.random.default_rng(3).normal(size=times().shape[0]))

    assert peaks.frames.shape[0] / peaks.frame_count <= NOISE_PEAKS_PER_FRAME_CEILING
