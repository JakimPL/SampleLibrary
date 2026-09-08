from __future__ import annotations

import librosa
import numpy as np
from numpy.typing import NDArray

from samplemorph.canonicalizers.common import prepare_mono, restore_spectrogram, to_sound_image
from samplemorph.geometry import LogFrequencyGeometry, log_frequency_geometry
from samplemorph.images import AnalysisSpectrogram, SoundImage


class LogFrequencyCanonicalizer:
    """Canonicalizes onto an exactly logarithmic reading of the short-time Fourier magnitude.

    Each band is read from the linear Fourier grid by interpolation at that band's own center
    frequency, and synthesis reads it back the same way, so the return path to audio is an ordinary
    magnitude inversion on the grid the analysis started from. That keeps an exact log axis --
    where a rate change is a whole-band translation -- and a well-behaved inverse at once.
    """

    def __init__(self, geometry: LogFrequencyGeometry) -> None:
        self._geometry = geometry

    @property
    def geometry(self) -> LogFrequencyGeometry:
        return self._geometry

    def canonicalize(self, waveform: NDArray[np.float64]) -> SoundImage:
        mono = prepare_mono(waveform)
        linear = np.abs(librosa.stft(mono, n_fft=self._geometry.fft_length, hop_length=self._geometry.hop_length))
        return to_sound_image(
            _onto_log_axis(linear, geometry=self._geometry), geometry=self._geometry, frame_count=mono.shape[0]
        )

    def restore(self, image: SoundImage) -> AnalysisSpectrogram:
        return restore_spectrogram(image, geometry=self._geometry)


def onto_linear_axis(magnitude: NDArray[np.float64], *, geometry: LogFrequencyGeometry) -> NDArray[np.float64]:
    """Read a logarithmic magnitude spectrogram back onto the linear Fourier frequency grid."""
    band_frequencies = geometry.band_frequencies
    linear_frequencies = geometry.linear_frequencies
    return np.stack([np.interp(linear_frequencies, band_frequencies, frame) for frame in magnitude.T]).T


def _onto_log_axis(linear: NDArray[np.float64], *, geometry: LogFrequencyGeometry) -> NDArray[np.float64]:
    band_frequencies = geometry.band_frequencies
    linear_frequencies = geometry.linear_frequencies
    return np.stack([np.interp(band_frequencies, linear_frequencies, frame) for frame in linear.T]).T


def build_log_frequency_canonicalizer() -> LogFrequencyCanonicalizer:
    return LogFrequencyCanonicalizer(log_frequency_geometry())
