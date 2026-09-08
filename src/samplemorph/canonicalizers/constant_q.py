from __future__ import annotations

import librosa
import numpy as np
from numpy.typing import NDArray

from samplemorph.canonicalizers.common import prepare_mono, restore_spectrogram, to_sound_image
from samplemorph.geometry import ConstantQGeometry, constant_q_geometry
from samplemorph.images import AnalysisSpectrogram, SoundImage


class ConstantQCanonicalizer:
    """Canonicalizes onto a constant-Q magnitude, logarithmic across its whole range by construction.

    Every bin carries the same number of cycles, so the frequency resolution follows pitch instead
    of a fixed Fourier window and the translation a rate change produces holds in the bass as
    exactly as in the treble. Synthesis reads the bins onto the linear Fourier grid by
    interpolation, so one magnitude inversion serves this axis as it serves the others and the
    comparison between axes runs through one shared return path.
    """

    def __init__(self, geometry: ConstantQGeometry) -> None:
        self._geometry = geometry

    @property
    def geometry(self) -> ConstantQGeometry:
        return self._geometry

    def canonicalize(self, waveform: NDArray[np.float64]) -> SoundImage:
        mono = prepare_mono(waveform)
        bands = np.abs(
            librosa.cqt(
                mono,
                sr=self._geometry.analysis_rate_hz,
                hop_length=self._geometry.hop_length,
                fmin=self._geometry.minimum_frequency_hz,
                bins_per_octave=self._geometry.bins_per_octave,
                n_bins=self._geometry.band_count,
            )
        )
        return to_sound_image(bands, geometry=self._geometry, frame_count=mono.shape[0])

    def restore(self, image: SoundImage) -> AnalysisSpectrogram:
        return restore_spectrogram(image, geometry=self._geometry)


def onto_linear_axis(magnitude: NDArray[np.float64], *, geometry: ConstantQGeometry) -> NDArray[np.float64]:
    """Read a constant-Q magnitude spectrogram onto the linear Fourier frequency grid."""
    band_frequencies = geometry.band_frequencies
    linear_frequencies = geometry.linear_frequencies
    return np.stack([np.interp(linear_frequencies, band_frequencies, frame) for frame in magnitude.T]).T


def build_constant_q_canonicalizer() -> ConstantQCanonicalizer:
    return ConstantQCanonicalizer(constant_q_geometry())
