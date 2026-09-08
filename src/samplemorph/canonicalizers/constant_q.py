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
    exactly as in the treble. That accuracy is what this axis supplies, and it locates a retuning
    on real material more often than the Fourier axes do.

    The bins measure amplitude per constant-Q band rather than per Fourier bin, and the two differ
    by around 20 dB over the lowest octaves, so this axis serves analysis while audio is
    synthesized from `LogFrequencyCanonicalizer`, whose bands share the Fourier grid's width.
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


def build_constant_q_canonicalizer() -> ConstantQCanonicalizer:
    return ConstantQCanonicalizer(constant_q_geometry())
