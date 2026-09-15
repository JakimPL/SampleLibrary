from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.geometry import LogFrequencyGeometry, log_frequency_geometry
from samplemorph.transport.analysis import TransportAnalysis, analyze
from samplemorph.transport.settings import TransportSettings

CLIP_FRAMES: Final[int] = 16384
HIT_DECAY_PER_SECOND: Final[float] = 30.0
TONE_WEIGHTS: Final[tuple[float, ...]] = (1.0, 0.5, 0.25, 0.125)
GEOMETRY: Final[LogFrequencyGeometry] = log_frequency_geometry()
BIN_SPACING_HZ: Final[float] = NOMINAL_WAV_RATE / GEOMETRY.fft_length


def analysis_of(mono: NDArray[np.float64]) -> TransportAnalysis:
    return analyze(prepare_mono(mono), rate_hz=NOMINAL_WAV_RATE, geometry=GEOMETRY, settings=TransportSettings())


def times(frame_count: int) -> NDArray[np.float64]:
    return np.arange(frame_count) / NOMINAL_WAV_RATE


def tone(
    frequency_hz: float, *, frame_count: int = CLIP_FRAMES, weights: tuple[float, ...] = TONE_WEIGHTS
) -> NDArray[np.float64]:
    seconds = times(frame_count)
    return np.sum(
        [weight * np.sin(2.0 * np.pi * frequency_hz * index * seconds) for index, weight in enumerate(weights, 1)],
        axis=0,
    )


def sines(frequencies_hz: tuple[float, ...], *, frame_count: int = CLIP_FRAMES) -> NDArray[np.float64]:
    seconds = times(frame_count)
    return np.sum([np.sin(2.0 * np.pi * frequency * seconds) for frequency in frequencies_hz], axis=0)


def decaying(
    mono: NDArray[np.float64], *, time_constant_seconds: float, delay_seconds: float = 0.0
) -> NDArray[np.float64]:
    since = times(mono.shape[0]) - delay_seconds
    envelope = np.where(since >= 0.0, np.exp(-np.maximum(since, 0.0) / time_constant_seconds), 0.0)
    return mono * envelope


def noise_band(
    lowest_hz: float, highest_hz: float, *, frame_count: int = CLIP_FRAMES, seed: int
) -> NDArray[np.float64]:
    spectrum = np.fft.rfft(np.random.default_rng(seed).normal(size=frame_count))
    frequencies = np.fft.rfftfreq(frame_count, 1.0 / NOMINAL_WAV_RATE)
    spectrum[(frequencies < lowest_hz) | (frequencies > highest_hz)] = 0.0
    return np.fft.irfft(spectrum, n=frame_count)


def middle_spectrum(magnitude: NDArray[np.float32]) -> NDArray[np.float64]:
    """The energy spectrum averaged over the middle half of the frames, clear of both edges."""
    frame_count = magnitude.shape[1]
    middle = magnitude[:, frame_count // 4 : max(3 * frame_count // 4, frame_count // 4 + 1)].astype(np.float64)
    spectrum: NDArray[np.float64] = (middle**2).mean(axis=1)
    return spectrum
