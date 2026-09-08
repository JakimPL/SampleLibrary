from __future__ import annotations

import librosa
import numpy as np
from numpy.typing import NDArray

from samplemorph.canonicalizers.common import prepare_mono, restore_spectrogram, to_sound_image
from samplemorph.geometry import MelGeometry, mel_geometry
from samplemorph.images import AnalysisSpectrogram, SoundImage

MEL_INVERSION_POWER: float = 1.0


class MelCanonicalizer:
    """Canonicalizes onto a mel filterbank, the reference the log-frequency axis is measured against.

    Mel bands approach a logarithm above roughly 1 kHz and stay close to linear below it, so a rate
    change moves content by a band count that depends on where the content sits. Keeping this axis
    registered alongside the exactly logarithmic one is what turns "does the frequency axis have to
    be logarithmic" into a measurement rather than an argument.
    """

    def __init__(self, geometry: MelGeometry) -> None:
        self._geometry = geometry

    @property
    def geometry(self) -> MelGeometry:
        return self._geometry

    def canonicalize(self, waveform: NDArray[np.float64]) -> SoundImage:
        mono = prepare_mono(waveform)
        bands = librosa.feature.melspectrogram(
            y=mono,
            sr=self._geometry.analysis_rate_hz,
            n_fft=self._geometry.fft_length,
            hop_length=self._geometry.hop_length,
            n_mels=self._geometry.band_count,
            power=MEL_INVERSION_POWER,
        )
        return to_sound_image(bands, geometry=self._geometry, frame_count=mono.shape[0])

    def restore(self, image: SoundImage) -> AnalysisSpectrogram:
        return restore_spectrogram(image, geometry=self._geometry)


def onto_linear_axis(magnitude: NDArray[np.float64], *, geometry: MelGeometry) -> NDArray[np.float64]:
    """Read a mel magnitude spectrogram back onto the linear Fourier frequency grid."""
    linear: NDArray[np.float64] = librosa.feature.inverse.mel_to_stft(
        magnitude,
        sr=geometry.analysis_rate_hz,
        n_fft=geometry.fft_length,
        power=MEL_INVERSION_POWER,
    )
    return linear


def build_mel_canonicalizer() -> MelCanonicalizer:
    return MelCanonicalizer(mel_geometry())
