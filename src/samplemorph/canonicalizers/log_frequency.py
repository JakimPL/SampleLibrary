from __future__ import annotations

import librosa
import numpy as np
from numpy.typing import NDArray

from samplecore.waveform import triangular_weights
from samplemorph.canonicalizers.common import prepare_mono, restore_spectrogram, to_sound_image
from samplemorph.geometry import LogFrequencyGeometry, log_frequency_geometry
from samplemorph.images import AnalysisSpectrogram, SoundImage


class LogFrequencyCanonicalizer:
    """Canonicalizes onto an exactly logarithmic reading of the short-time Fourier magnitude.

    Each band averages the linear Fourier bins across its own width, and synthesis reads the bands
    back onto that grid by interpolation, so the return path to audio is an ordinary magnitude
    inversion on the grid the analysis started from. That keeps an exact log axis -- where a rate
    change is a whole-band translation -- and a well-behaved inverse at once.
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


def _onto_log_axis(linear: NDArray[np.float64], *, geometry: LogFrequencyGeometry) -> NDArray[np.float64]:
    bands: NDArray[np.float64] = band_weights(geometry) @ linear
    return bands


def band_weights(geometry: LogFrequencyGeometry) -> NDArray[np.float64]:
    """Weights averaging the linear Fourier bins each logarithmic band covers.

    A band spans one Fourier bin at around 560 Hz and widens with frequency from there, reaching
    about forty bins at the top of the range. Each band therefore takes a weighted mean over its
    own width, which carries every bin it covers into the picture and holds each frame's content
    where the analysis found it.

    Bands narrower than one bin widen to that much, so every band draws on the grid it is read
    from. Weights fall linearly from each band's center to its edge and sum to one per band.
    """
    band_frequencies = geometry.band_frequencies
    step = 2.0 ** (1.0 / geometry.bins_per_octave)
    bin_spacing = geometry.analysis_rate_hz / geometry.fft_length
    return triangular_weights(
        source_positions=geometry.linear_frequencies,
        target_positions=band_frequencies,
        half_widths=np.maximum(band_frequencies * (step - 1.0 / step) / 2.0, bin_spacing),
    )


def build_log_frequency_canonicalizer() -> LogFrequencyCanonicalizer:
    return LogFrequencyCanonicalizer(log_frequency_geometry())
