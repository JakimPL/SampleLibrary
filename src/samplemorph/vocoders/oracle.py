from __future__ import annotations

import librosa
import numpy as np
from numpy.typing import NDArray

from samplemorph.canonicalizers.common import analysis_transform
from samplemorph.canonicalizers.linear_axis import onto_linear_axis
from samplemorph.geometry import analysis_taper
from samplemorph.images import AnalysisSpectrogram


class OraclePhaseVocoder:
    """Reuses a known waveform's own phase, reporting what a perfect phase estimate would leave.

    This is a measuring instrument rather than a way to make new sound: it needs the very signal a
    vocoder is supposed to be recovering. Set beside an estimating vocoder, it separates what the
    frequency axis and the grid throw away from what the phase estimate throws away, which is what
    decides whether a better vocoder is worth training.
    """

    def __init__(self, reference: NDArray[np.float64]) -> None:
        self._reference = reference

    def synthesize(self, spectrogram: AnalysisSpectrogram) -> NDArray[np.float64]:
        geometry = spectrogram.geometry
        linear = onto_linear_axis(spectrogram.magnitude, geometry=geometry)
        reference = analysis_transform(self._reference, geometry=geometry)
        frames = min(linear.shape[1], reference.shape[1])
        phase = np.exp(1j * np.angle(reference[:, :frames]))
        waveform: NDArray[np.float64] = librosa.istft(
            linear[:, :frames] * phase,
            hop_length=geometry.hop_length,
            n_fft=geometry.fft_length,
            window=analysis_taper(geometry),
            length=spectrogram.frame_count,
        )
        return waveform
