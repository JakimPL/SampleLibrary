from __future__ import annotations

from enum import StrEnum, unique
from typing import Annotated, Final, Literal

import librosa
import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, Field
from scipy.signal import get_window
from scipy.signal.windows import gaussian

from samplecore.models.base import FROZEN
from samplecore.storage.audio_store import NOMINAL_WAV_RATE

SEMITONES_PER_OCTAVE: Final[int] = 12
REFERENCE_FREQUENCY_HZ: Final[float] = 440.0
MINIMUM_FREQUENCY_HZ: Final[float] = 32.70
DEFAULT_HOP_LENGTH: Final[int] = 256
DEFAULT_FFT_LENGTH: Final[int] = 2048
DEFAULT_TIME_COLUMNS: Final[int] = 64
DEFAULT_DYNAMIC_RANGE_DB: Final[float] = 100.0
DEFAULT_MAXIMUM_SHIFT_SEMITONES: Final[float] = 48.0
DEFAULT_MEL_BAND_COUNT: Final[int] = 128
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


@unique
class Anchor(StrEnum):
    """Which band of a sound alignment moves to the reference band, if any.

    `NONE` keeps the picture where the analysis read it: every band holds the frequency it measured,
    a kick and a pad alike, and the grid is exactly as tall as the analysis range. `LOUDEST` moves
    the band carrying the most energy over the whole sound, which every kind of material has.
    `FUNDAMENTAL` moves the band a harmonic series is built on, so two sounds playing one note align
    on that note whichever of their partials is the strongest, and a morph between them keeps its
    pitch on the line between theirs.
    """

    NONE = "none"
    LOUDEST = "loudest"
    FUNDAMENTAL = "fundamental"


DEFAULT_ANCHOR: Final[Anchor] = Anchor.NONE


def shift_headroom_bands(*, anchor: Anchor, maximum_shift_semitones: float, bands_per_semitone: float) -> int:
    """How many empty bands a grid carries at each end, so an anchoring rule moves content without losing it.

    Alignment translates the whole picture along the frequency axis, and a grid exactly as tall as
    the analysis range would push whatever passes its edge out of the picture. Reserving the largest
    shift at both ends keeps every band that entered the grid inside it, whatever pitch a sample sat
    at -- which matters most for bass material, whose distance from the reference band is greatest.
    A picture nothing moves needs no room to move in, so it stays as tall as the analysis.
    """
    if anchor is Anchor.NONE:
        return 0
    return int(round(maximum_shift_semitones * bands_per_semitone))


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
    anchor: Anchor = DEFAULT_ANCHOR
    analysis_window: AnalysisWindow = DEFAULT_ANALYSIS_WINDOW
    analysis_rate_hz: int
    fft_length: int
    hop_length: int
    minimum_frequency_hz: float
    bins_per_octave: int
    band_count: int
    time_columns: int
    dynamic_range_db: float
    maximum_shift_semitones: float

    @property
    def shift_headroom_bands(self) -> int:
        return shift_headroom_bands(
            anchor=self.anchor,
            maximum_shift_semitones=self.maximum_shift_semitones,
            bands_per_semitone=self.bands_per_semitone,
        )

    @property
    def grid_shape(self) -> tuple[int, int]:
        return self.band_count + 2 * self.shift_headroom_bands, self.time_columns

    @property
    def bands_per_semitone(self) -> float:
        return self.bins_per_octave / SEMITONES_PER_OCTAVE

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

    @property
    def reference_band(self) -> int:
        """The band an aligned image's anchor is moved to, at `REFERENCE_FREQUENCY_HZ`."""
        return int(round(self.bins_per_octave * np.log2(REFERENCE_FREQUENCY_HZ / self.minimum_frequency_hz)))


class MelGeometry(BaseModel):
    """A short-time Fourier magnitude read onto a mel filterbank.

    The mel scale approaches a logarithm above roughly 1 kHz and stays close to linear below it, so
    a rate change moves content by a band count that varies with where the content sits. The
    conversion below reports the local rate at the reference band, which is exact there and
    approaches the truth as content sits nearer to it.
    """

    model_config = FROZEN

    kind: Literal["mel"] = "mel"
    anchor: Anchor = DEFAULT_ANCHOR
    analysis_rate_hz: int
    fft_length: int
    hop_length: int
    band_count: int
    time_columns: int
    dynamic_range_db: float
    maximum_shift_semitones: float

    @property
    def shift_headroom_bands(self) -> int:
        return shift_headroom_bands(
            anchor=self.anchor,
            maximum_shift_semitones=self.maximum_shift_semitones,
            bands_per_semitone=self.bands_per_semitone,
        )

    @property
    def grid_shape(self) -> tuple[int, int]:
        return self.band_count + 2 * self.shift_headroom_bands, self.time_columns

    @property
    def band_frequencies(self) -> NDArray[np.float64]:
        frequencies: NDArray[np.float64] = librosa.mel_frequencies(
            n_mels=self.band_count, fmin=0.0, fmax=self.analysis_rate_hz / 2
        )
        return frequencies

    @property
    def reference_band(self) -> int:
        return int(np.argmin(np.abs(self.band_frequencies - REFERENCE_FREQUENCY_HZ)))

    @property
    def bands_per_semitone(self) -> float:
        """How many bands one semitone spans at the reference band.

        Read as a local slope: the band frequencies either side of `reference_band` give the ratio
        one band step covers there, and a semitone is `2 ** (1/12)`.
        """
        frequencies = self.band_frequencies
        band = min(max(self.reference_band, 1), self.band_count - 1)
        octaves_per_band = float(np.log2(frequencies[band] / frequencies[band - 1]))
        return 1.0 / (octaves_per_band * SEMITONES_PER_OCTAVE)


class ConstantQGeometry(BaseModel):
    """A constant-Q magnitude, logarithmic by construction across its whole range.

    Every bin carries the same number of cycles, so resolution follows pitch rather than a fixed
    Fourier window, and the translation a rate change produces is exact in the bass as well as the
    treble. That makes this the axis that locates a retuning most accurately, which is what it is
    kept for.

    A bin states the amplitude the signal carries within a band whose width grows with its center
    frequency, so its value stands in a different relation to the waveform than a Fourier
    magnitude, which reads a band of one fixed width. Measurement puts the gap between the two at
    roughly 20 dB across the lowest octaves, so audio is synthesized from an axis whose bins share
    the Fourier grid's own width.
    """

    model_config = FROZEN

    kind: Literal["constant_q"] = "constant_q"
    anchor: Anchor = DEFAULT_ANCHOR
    analysis_rate_hz: int
    fft_length: int
    hop_length: int
    minimum_frequency_hz: float
    bins_per_octave: int
    band_count: int
    time_columns: int
    dynamic_range_db: float
    maximum_shift_semitones: float

    @property
    def shift_headroom_bands(self) -> int:
        return shift_headroom_bands(
            anchor=self.anchor,
            maximum_shift_semitones=self.maximum_shift_semitones,
            bands_per_semitone=self.bands_per_semitone,
        )

    @property
    def grid_shape(self) -> tuple[int, int]:
        return self.band_count + 2 * self.shift_headroom_bands, self.time_columns

    @property
    def bands_per_semitone(self) -> float:
        return self.bins_per_octave / SEMITONES_PER_OCTAVE

    @property
    def band_frequencies(self) -> NDArray[np.float64]:
        return self.minimum_frequency_hz * 2.0 ** (np.arange(self.band_count) / self.bins_per_octave)

    @property
    def linear_frequencies(self) -> NDArray[np.float64]:
        frequencies: NDArray[np.float64] = librosa.fft_frequencies(sr=self.analysis_rate_hz, n_fft=self.fft_length)
        return frequencies

    @property
    def reference_band(self) -> int:
        return int(round(self.bins_per_octave * np.log2(REFERENCE_FREQUENCY_HZ / self.minimum_frequency_hz)))


Geometry = Annotated[LogFrequencyGeometry | MelGeometry | ConstantQGeometry, Field(discriminator="kind")]


def analysis_taper(geometry: Geometry) -> NDArray[np.float64]:
    """The taper one frame of this geometry's analysis is read through, one point per transform sample.

    The Hann taper is the periodic one an overlapped analysis sums cleanly. The Gaussian is drawn
    at twice the length and every other point kept, so its peak lands between two samples -- the
    sampling phase gradient heap integration is derived for. An axis with no taper of its own reads
    through the Hann.
    """
    match geometry:
        case LogFrequencyGeometry(analysis_window=AnalysisWindow.GAUSSIAN):
            return gaussian_taper(geometry.fft_length)
        case _:
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


def frames_per_phase_turn(*, fft_length: int, hop_length: int) -> int:
    """How many frames a bin one step above the lowest takes to bring its phase back round.

    A bin advances by a fixed angle each hop, set by the window and the step alone, so this says how
    fast the phase turns before anything about the sound is taken into account.
    """
    return max(fft_length // hop_length, 1)


def bands_reaching_nyquist(*, analysis_rate_hz: int, minimum_frequency_hz: float, bins_per_octave: int) -> int:
    """How many logarithmic bands reach from `minimum_frequency_hz` to the Nyquist frequency.

    The highest band sits at or above Nyquist, so the bands cover every Fourier bin the analysis
    produces and synthesis reads each one from a band that measured it. A sample plays back well
    below the nominal rate the store writes, which puts the top of this range within hearing.
    """
    octaves = np.log2((analysis_rate_hz / 2) / minimum_frequency_hz)
    return int(np.ceil(bins_per_octave * octaves)) + 1


def bands_below_nyquist(*, analysis_rate_hz: int, minimum_frequency_hz: float, bins_per_octave: int) -> int:
    """How many logarithmic bands fit between `minimum_frequency_hz` and the Nyquist frequency.

    Every band stays below Nyquist, which is what a transform building a wavelet per band asks
    for.
    """
    return int(np.floor(bins_per_octave * np.log2((analysis_rate_hz / 2) / minimum_frequency_hz)))


def log_frequency_geometry(
    *,
    bins_per_octave: int = DEFAULT_BINS_PER_OCTAVE,
    anchor: Anchor = DEFAULT_ANCHOR,
    analysis_window: AnalysisWindow = DEFAULT_ANALYSIS_WINDOW,
) -> LogFrequencyGeometry:
    return LogFrequencyGeometry(
        anchor=anchor,
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
        time_columns=DEFAULT_TIME_COLUMNS,
        dynamic_range_db=DEFAULT_DYNAMIC_RANGE_DB,
        maximum_shift_semitones=DEFAULT_MAXIMUM_SHIFT_SEMITONES,
    )


def mel_geometry(*, band_count: int = DEFAULT_MEL_BAND_COUNT, anchor: Anchor = DEFAULT_ANCHOR) -> MelGeometry:
    return MelGeometry(
        anchor=anchor,
        analysis_rate_hz=NOMINAL_WAV_RATE,
        fft_length=DEFAULT_FFT_LENGTH,
        hop_length=DEFAULT_HOP_LENGTH,
        band_count=band_count,
        time_columns=DEFAULT_TIME_COLUMNS,
        dynamic_range_db=DEFAULT_DYNAMIC_RANGE_DB,
        maximum_shift_semitones=DEFAULT_MAXIMUM_SHIFT_SEMITONES,
    )


def constant_q_geometry(
    *, bins_per_octave: int = DEFAULT_CONSTANT_Q_BINS_PER_OCTAVE, anchor: Anchor = DEFAULT_ANCHOR
) -> ConstantQGeometry:
    return ConstantQGeometry(
        anchor=anchor,
        analysis_rate_hz=NOMINAL_WAV_RATE,
        fft_length=DEFAULT_FFT_LENGTH,
        hop_length=DEFAULT_HOP_LENGTH,
        minimum_frequency_hz=MINIMUM_FREQUENCY_HZ,
        bins_per_octave=bins_per_octave,
        band_count=bands_below_nyquist(
            analysis_rate_hz=NOMINAL_WAV_RATE,
            minimum_frequency_hz=MINIMUM_FREQUENCY_HZ,
            bins_per_octave=bins_per_octave,
        ),
        time_columns=DEFAULT_TIME_COLUMNS,
        dynamic_range_db=DEFAULT_DYNAMIC_RANGE_DB,
        maximum_shift_semitones=DEFAULT_MAXIMUM_SHIFT_SEMITONES,
    )
