from __future__ import annotations

from typing import Final

import librosa
import numpy as np
from numpy.typing import NDArray

HELD_OUT_FFT_LENGTH: Final[int] = 1024
HELD_OUT_HOP_LENGTH: Final[int] = 256
HELD_OUT_FLOOR_DB: Final[float] = 80.0
SILENT_LEVEL: Final[float] = 1e-10


def held_out_spectrum(waveform: NDArray[np.float64]) -> NDArray[np.float64]:
    """A waveform's log magnitudes on a linear Fourier grid, the yardstick audio distances use here.

    The analysis is fixed and shared, so two canonicalizers are compared on one scale whichever axis
    produced the audio. Reading it on the linear grid keeps every band the same width, which is what
    makes the yardstick report a spectrum whose shape is wrong: a filterbank averages neighboring
    bands together and returns a small number for a large error spread across them.

    Magnitudes are read relative to the waveform's own peak and held at `HELD_OUT_FLOOR_DB` below
    it, so the comparison covers the range a listener hears and states a distance in decibels.
    """
    magnitude = np.abs(
        librosa.stft(_peak_normalized(waveform), n_fft=HELD_OUT_FFT_LENGTH, hop_length=HELD_OUT_HOP_LENGTH)
    )
    floor = 10.0 ** (-HELD_OUT_FLOOR_DB / 20.0)
    decibels: NDArray[np.float64] = 20.0 * np.log10(np.maximum(magnitude, floor))
    return decibels


def held_out_distance_db(first: NDArray[np.float64], second: NDArray[np.float64]) -> float:
    """Root-mean-square difference between two held-out spectra, over the frames they share."""
    width = min(first.shape[1], second.shape[1])
    return float(np.sqrt(np.mean((first[:, :width] - second[:, :width]) ** 2)))


def grid_distance(first: NDArray[np.float64], second: NDArray[np.float64]) -> float:
    """Root-mean-square difference between two canonical grids."""
    return float(np.sqrt(np.mean((first - second) ** 2)))


def _peak_normalized(waveform: NDArray[np.float64]) -> NDArray[np.float64]:
    peak = float(np.abs(waveform).max())
    return waveform / peak if peak > SILENT_LEVEL else waveform
