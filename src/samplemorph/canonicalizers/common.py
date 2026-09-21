from __future__ import annotations

import warnings
from typing import Final, NewType

import librosa
import numpy as np
from numpy.typing import NDArray

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplecore.waveform import fold_to_mono, remove_subsonic
from samplemorph.geometry import LogFrequencyGeometry, analysis_taper

HARMONIC_COUNT: Final[int] = 8
HARMONIC_DECAY: Final[float] = 0.84
SHORT_SIGNAL_WARNING: Final[str] = r"n_fft=\d+ is too large for input signal"

# One channel of frames that has come in through `prepare_mono`, or a retuning of such frames.
PreparedMono = NewType("PreparedMono", NDArray[np.float64])


def prepare_mono(waveform: NDArray[np.float64]) -> PreparedMono:
    """Fold a stored waveform to the one audible channel every frequency axis analyzes.

    The band below hearing leaves here, at the pipeline's way in and nowhere else, so every
    analysis, every reconstruction and every reference a reconstruction is measured against carries
    the same content a listener does, filtered once. The filter is designed at the nominal
    container rate, which is the rate every frequency axis reads its frames at.
    """
    return PreparedMono(remove_subsonic(fold_to_mono(waveform), sample_rate_hz=NOMINAL_WAV_RATE))


def analysis_transform(mono: NDArray[np.float64], *, geometry: LogFrequencyGeometry) -> NDArray[np.complex128]:
    """The short-time Fourier transform a prepared waveform is read through on this geometry.

    One frame per hop through the geometry's taper, centered so the first frame sits on the
    waveform's start. A hit shorter than one transform is read the same way: librosa pads half a
    transform of silence on each side before framing, so the hit fills the few frames its length
    gives it, and the length warning librosa raises on the way stays out of the logs.
    """
    with warnings.catch_warnings():
        # librosa warns about a signal shorter than n_fft and analyzes it regardless.
        warnings.filterwarnings("ignore", message=SHORT_SIGNAL_WARNING, category=UserWarning)
        transform: NDArray[np.complex128] = librosa.stft(
            mono, n_fft=geometry.fft_length, hop_length=geometry.hop_length, window=analysis_taper(geometry)
        )
    return transform


def to_magnitudes(grid: NDArray[np.float64], *, dynamic_range_db: float, log_gain: float) -> NDArray[np.float64]:
    """Undo `to_normalized_decibels`, returning the linear magnitudes a vocoder can invert."""
    decibels = (grid - 1.0) * dynamic_range_db
    magnitudes: NDArray[np.float64] = 10.0 ** (decibels / 20.0) * 2.0**log_gain
    return magnitudes


def harmonic_sum(profile: NDArray[np.float64], *, frequencies: NDArray[np.float64]) -> NDArray[np.float64]:
    """Every band's score as a fundamental: the magnitude at its first `HARMONIC_COUNT` multiples, each counting less by `HARMONIC_DECAY`.

    `profile` is a linear magnitude over bands centered at `frequencies`, and a multiple beyond the
    highest band reads as silence.
    """
    total = np.zeros_like(profile)
    for harmonic in range(1, HARMONIC_COUNT + 1):
        total += HARMONIC_DECAY ** (harmonic - 1) * np.interp(harmonic * frequencies, frequencies, profile, right=0.0)
    return total
