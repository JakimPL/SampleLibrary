from __future__ import annotations

from typing import Annotated, Final, Literal

import librosa
import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, Field

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
DEFAULT_BINS_PER_OCTAVE: Final[int] = 144
DEFAULT_MEL_BAND_COUNT: Final[int] = 128
DEFAULT_CONSTANT_Q_BINS_PER_OCTAVE: Final[int] = 36


def shift_headroom_bands(*, maximum_shift_semitones: float, bands_per_semitone: float) -> int:
    """How many empty bands a grid carries at each end, so alignment moves content without losing it.

    Alignment translates the whole picture along the frequency axis, and a grid exactly as tall as
    the analysis range would push whatever passes its edge out of the picture. Reserving the largest
    shift at both ends keeps every band that entered the grid inside it, whatever pitch a sample sat
    at -- which matters most for bass material, whose distance from the reference band is greatest.
    """
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
            maximum_shift_semitones=self.maximum_shift_semitones, bands_per_semitone=self.bands_per_semitone
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
        """The band an aligned image's dominant partial is moved to, at `REFERENCE_FREQUENCY_HZ`."""
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
            maximum_shift_semitones=self.maximum_shift_semitones, bands_per_semitone=self.bands_per_semitone
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
            maximum_shift_semitones=self.maximum_shift_semitones, bands_per_semitone=self.bands_per_semitone
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


def log_frequency_geometry(*, bins_per_octave: int = DEFAULT_BINS_PER_OCTAVE) -> LogFrequencyGeometry:
    return LogFrequencyGeometry(
        analysis_rate_hz=NOMINAL_WAV_RATE,
        fft_length=DEFAULT_FFT_LENGTH,
        hop_length=DEFAULT_HOP_LENGTH,
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


def mel_geometry(*, band_count: int = DEFAULT_MEL_BAND_COUNT) -> MelGeometry:
    return MelGeometry(
        analysis_rate_hz=NOMINAL_WAV_RATE,
        fft_length=DEFAULT_FFT_LENGTH,
        hop_length=DEFAULT_HOP_LENGTH,
        band_count=band_count,
        time_columns=DEFAULT_TIME_COLUMNS,
        dynamic_range_db=DEFAULT_DYNAMIC_RANGE_DB,
        maximum_shift_semitones=DEFAULT_MAXIMUM_SHIFT_SEMITONES,
    )


def constant_q_geometry(*, bins_per_octave: int = DEFAULT_CONSTANT_Q_BINS_PER_OCTAVE) -> ConstantQGeometry:
    return ConstantQGeometry(
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
