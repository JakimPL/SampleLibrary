from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.partials.peaks import SpectralPeaks, analysis_length, gaussian_transform, pick_peaks
from samplemorph.partials.settings import PartialSettings
from samplemorph.partials.tracks import PartialTracks, track_peaks

RATE_HZ: Final[float] = float(NOMINAL_WAV_RATE)
HOP_LENGTH: Final[int] = 128
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
