from __future__ import annotations

from typing import Final

import librosa
import numpy as np
from numpy.typing import NDArray

from samplecore.storage.audio_store import NOMINAL_WAV_RATE

COMPARISON_FFT_LENGTH: Final[int] = 1024
COMPARISON_HOP_LENGTH: Final[int] = 256
COMPARISON_BAND_COUNT: Final[int] = 128
SILENT_LEVEL: Final[float] = 1e-10


def log_mel_spectrum(waveform: NDArray[np.float64]) -> NDArray[np.float64]:
    """A waveform's log-mel magnitudes, the yardstick this project states audio distances in.

    Holding one fixed analysis here, independent of whichever frequency axis produced the audio,
    is what lets two canonicalizers be compared on the same scale.
    """
    power = librosa.feature.melspectrogram(
        y=_peak_normalized(waveform),
        sr=NOMINAL_WAV_RATE,
        n_fft=COMPARISON_FFT_LENGTH,
        hop_length=COMPARISON_HOP_LENGTH,
        n_mels=COMPARISON_BAND_COUNT,
    )
    decibels: NDArray[np.float64] = librosa.power_to_db(power, ref=1.0, top_db=None)
    return decibels


def log_mel_distance_db(first: NDArray[np.float64], second: NDArray[np.float64]) -> float:
    """Root-mean-square difference between two log-mel spectra, over the frames they share."""
    width = min(first.shape[1], second.shape[1])
    return float(np.sqrt(np.mean((first[:, :width] - second[:, :width]) ** 2)))


def grid_distance(first: NDArray[np.float64], second: NDArray[np.float64]) -> float:
    """Root-mean-square difference between two canonical grids."""
    return float(np.sqrt(np.mean((first - second) ** 2)))


def _peak_normalized(waveform: NDArray[np.float64]) -> NDArray[np.float64]:
    peak = float(np.abs(waveform).max())
    return waveform / peak if peak > SILENT_LEVEL else waveform
