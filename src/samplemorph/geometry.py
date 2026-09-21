from __future__ import annotations

from enum import StrEnum, unique
from typing import Final, Literal

import librosa
import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel
from scipy.signal import get_window
from scipy.signal.windows import gaussian

from samplecore.models.base import FROZEN
from samplecore.storage.audio_store import NOMINAL_WAV_RATE

SEMITONES_PER_OCTAVE: Final[int] = 12
REFERENCE_FREQUENCY_HZ: Final[float] = 440.0
MINIMUM_FREQUENCY_HZ: Final[float] = 32.70
DEFAULT_HOP_LENGTH: Final[int] = 256
DEFAULT_FFT_LENGTH: Final[int] = 2048
DEFAULT_DYNAMIC_RANGE_DB: Final[float] = 100.0
DEFAULT_CONSTANT_Q_BINS_PER_OCTAVE: Final[int] = 36
GAUSSIAN_EDGE_LEVEL: Final[float] = 0.01
# 288 bands per octave keep 77% of the Fourier magnitude's degrees of freedom through the band
# matrix (144 kept 53%), and phase gradient heap integration reads its gradients cleanly from a
# transform at least sixteen times its hop (Prusa, Balazs and Sondergaard, 2017).
DEFAULT_BINS_PER_OCTAVE: Final[int] = 288
PHASE_GRADIENT_REDUNDANCY: Final[int] = 16
DEFAULT_LOG_FREQUENCY_HOP_LENGTH: Final[int] = DEFAULT_FFT_LENGTH // PHASE_GRADIENT_REDUNDANCY


@unique
class AnalysisWindow(StrEnum):
    """The taper a short-time Fourier analysis reads each frame through.

    `HANN` is the ordinary analysis every magnitude inversion accepts. `GAUSSIAN` is the one taper
    whose phase gradient is a closed form of its magnitude gradient, which is what lets phase
    gradient heap integration recover a phase from the magnitude alone, and is the analysis the
    production geometry reads through.
    """

    HANN = "hann"
    GAUSSIAN = "gaussian"


DEFAULT_ANALYSIS_WINDOW: Final[AnalysisWindow] = AnalysisWindow.GAUSSIAN


def semitones_from_reference(frequency_hz: float) -> float:
    """How far a frequency lies from `REFERENCE_FREQUENCY_HZ`, in semitones, the scale every pitch reading states."""
    return SEMITONES_PER_OCTAVE * float(np.log2(frequency_hz / REFERENCE_FREQUENCY_HZ))


class LogFrequencyGeometry(BaseModel):
    """A short-time Fourier magnitude read onto an exactly logarithmic frequency axis.

    Bin centers sit at ``minimum_frequency_hz * 2 ** (index / bins_per_octave)``, so reading the
    same waveform at a different rate translates the image by a whole number of bins whenever the
    rate ratio is a whole number of ``bins_per_octave`` steps. Synthesis reads the axis back onto
    the linear Fourier grid it came from, which keeps the return path to audio an ordinary
    magnitude inversion.
    """

    model_config = FROZEN

    kind: Literal["log_frequency"] = "log_frequency"
    analysis_window: AnalysisWindow = DEFAULT_ANALYSIS_WINDOW
    analysis_rate_hz: int
    fft_length: int
    hop_length: int
    minimum_frequency_hz: float
    bins_per_octave: int
    band_count: int
    dynamic_range_db: float

    @property
    def gaussian_spread(self) -> float:
        return gaussian_spread(self.fft_length)

    @property
    def phase_gradient_spread(self) -> float:
        """The constant relating a Gaussian analysis's phase gradient to its magnitude gradient, ``2 pi spread^2``."""
        return float(2.0 * np.pi * self.gaussian_spread**2)

    @property
    def band_frequencies(self) -> NDArray[np.float64]:
        return self.minimum_frequency_hz * 2.0 ** (np.arange(self.band_count) / self.bins_per_octave)

    @property
    def linear_frequencies(self) -> NDArray[np.float64]:
        frequencies: NDArray[np.float64] = librosa.fft_frequencies(sr=self.analysis_rate_hz, n_fft=self.fft_length)
        return frequencies


def analysis_taper(geometry: LogFrequencyGeometry) -> NDArray[np.float64]:
    """The taper one frame of this geometry's analysis is read through, one point per transform sample.

    The Hann taper is the periodic one an overlapped analysis sums cleanly. The Gaussian is drawn
    at twice the length and every other point kept, so its peak lands between two samples -- the
    sampling phase gradient heap integration is derived for.
    """
    match geometry.analysis_window:
        case AnalysisWindow.GAUSSIAN:
            return gaussian_taper(geometry.fft_length)
        case AnalysisWindow.HANN:
            hann: NDArray[np.float64] = get_window("hann", geometry.fft_length, fftbins=True)
            return hann


def gaussian_spread(length: int) -> float:
    """The time spread, in samples, of a Gaussian taper `length` samples long that falls to `GAUSSIAN_EDGE_LEVEL` at its edges."""
    return float(np.sqrt(-(length**2) / (8.0 * np.log(GAUSSIAN_EDGE_LEVEL))))


def gaussian_taper(length: int) -> NDArray[np.float64]:
    """A Gaussian taper `length` samples long, drawn at twice the length with every other point kept.

    The peak lands between two samples, which is the sampling phase gradient heap integration is
    derived for, and every analysis under a Gaussian reads through the same rule whatever its length.
    """
    taper: NDArray[np.float64] = gaussian(2 * length + 1, 2.0 * gaussian_spread(length), sym=False)
    return taper[1 : 2 * length + 1 : 2]


def fourier_bin_count(*, fft_length: int) -> int:
    """How many Fourier bins one analysis window produces.

    Every axis returns to audio through this grid, whichever bands it carries its own picture on, so
    this is the width a vocoder reads and writes.
    """
    return fft_length // 2 + 1


def bands_reaching_nyquist(*, analysis_rate_hz: int, minimum_frequency_hz: float, bins_per_octave: int) -> int:
    """How many logarithmic bands reach from `minimum_frequency_hz` to the Nyquist frequency.

    The highest band sits at or above Nyquist, so the bands cover every Fourier bin the analysis
    produces and synthesis reads each one from a band that measured it. A sample plays back well
    below the nominal rate the store writes, which puts the top of this range within hearing.
    """
    octaves = np.log2((analysis_rate_hz / 2) / minimum_frequency_hz)
    return int(np.ceil(bins_per_octave * octaves)) + 1


def log_frequency_geometry(
    *,
    bins_per_octave: int = DEFAULT_BINS_PER_OCTAVE,
    analysis_window: AnalysisWindow = DEFAULT_ANALYSIS_WINDOW,
) -> LogFrequencyGeometry:
    return LogFrequencyGeometry(
        analysis_window=analysis_window,
        analysis_rate_hz=NOMINAL_WAV_RATE,
        fft_length=DEFAULT_FFT_LENGTH,
        hop_length=DEFAULT_LOG_FREQUENCY_HOP_LENGTH,
        minimum_frequency_hz=MINIMUM_FREQUENCY_HZ,
        bins_per_octave=bins_per_octave,
        band_count=bands_reaching_nyquist(
            analysis_rate_hz=NOMINAL_WAV_RATE,
            minimum_frequency_hz=MINIMUM_FREQUENCY_HZ,
            bins_per_octave=bins_per_octave,
        ),
        dynamic_range_db=DEFAULT_DYNAMIC_RANGE_DB,
    )
