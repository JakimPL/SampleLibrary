from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.geometry import LogFrequencyGeometry, log_frequency_geometry
from samplemorph.partials.model import SinusoidalModel, analyze_model
from samplemorph.partials.peaks import SpectralPeaks, analysis_length, gaussian_transform, pick_peaks
from samplemorph.partials.settings import PartialSettings
from samplemorph.partials.tracks import PartialTracks, track_peaks
from samplemorph.transport.settings import TransportSettings

RATE_HZ: Final[float] = float(NOMINAL_WAV_RATE)
GEOMETRY: Final[LogFrequencyGeometry] = log_frequency_geometry()
HOP_LENGTH: Final[int] = GEOMETRY.hop_length
SECONDS: Final[float] = 1.0
SETTINGS: Final[PartialSettings] = PartialSettings()


def times(seconds: float = SECONDS) -> NDArray[np.float64]:
    return np.arange(int(seconds * RATE_HZ)) / RATE_HZ


def peaks_of(waveform: NDArray[np.float64], *, settings: PartialSettings = SETTINGS) -> SpectralPeaks:
    window_length = analysis_length(RATE_HZ, settings=settings)
    return pick_peaks(
        gaussian_transform(waveform, window_length=window_length, hop_length=HOP_LENGTH),
        rate_hz=RATE_HZ,
        window_length=window_length,
        settings=settings,
    )


def tracks_of(waveform: NDArray[np.float64], *, settings: PartialSettings = SETTINGS) -> PartialTracks:
    return track_peaks(peaks_of(waveform, settings=settings), hop_length=HOP_LENGTH, rate_hz=RATE_HZ, settings=settings)


def model_of(waveform: NDArray[np.float64], *, settings: PartialSettings = SETTINGS) -> SinusoidalModel:
    return analyze_model(
        prepare_mono(waveform),
        rate_hz=RATE_HZ,
        geometry=GEOMETRY,
        transport_settings=TransportSettings(),
        partial_settings=settings,
    )


def harmonics(
    fundamental_hz: float, *, harmonic_count: int, seconds: float = SECONDS, brightness: float = 1.0
) -> NDArray[np.float64]:
    """A tone whose harmonic `k` sounds at `brightness ** (k - 1) / k` of the first, peaking at half of full scale."""
    seconds_axis = times(seconds)
    tone = np.sum(
        [
            brightness ** (harmonic - 1) * np.sin(2.0 * np.pi * fundamental_hz * harmonic * seconds_axis) / harmonic
            for harmonic in range(1, harmonic_count + 1)
        ],
        axis=0,
    )
    scaled: NDArray[np.float64] = 0.5 * tone / np.abs(tone).max()
    return scaled


def noise_hit(*, seconds: float = SECONDS, decay_per_second: float = 12.0, seed: int) -> NDArray[np.float64]:
    """A burst of noise falling away, the shape of a sound holding no partial at all."""
    seconds_axis = times(seconds)
    hit: NDArray[np.float64] = (
        0.5 * np.random.default_rng(seed).normal(size=seconds_axis.shape[0]) * np.exp(-decay_per_second * seconds_axis)
    )
    return hit


def vibrato_frequency(
    frame_times: NDArray[np.float64], *, fundamental_hz: float, depth_cents: float, rate_hz: float
) -> NDArray[np.float64]:
    frequency: NDArray[np.float64] = fundamental_hz * 2.0 ** (
        depth_cents / 1200.0 * np.sin(2.0 * np.pi * rate_hz * frame_times)
    )
    return frequency


def vibrato_tone(
    *, fundamental_hz: float, depth_cents: float, rate_hz: float, harmonic_count: int, seconds: float = SECONDS
) -> NDArray[np.float64]:
    """A tone of `harmonic_count` harmonics at 1/k, its pitch swinging sinusoidally by `depth_cents` at `rate_hz`."""
    frequency = vibrato_frequency(
        times(seconds), fundamental_hz=fundamental_hz, depth_cents=depth_cents, rate_hz=rate_hz
    )
    phase = 2.0 * np.pi * np.cumsum(frequency) / RATE_HZ
    tone: NDArray[np.float64] = np.sum([np.sin(k * phase) / k for k in range(1, harmonic_count + 1)], axis=0)
    return tone
