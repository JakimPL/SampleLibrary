from __future__ import annotations

from typing import Final

import librosa
import numpy as np
from numpy.typing import NDArray

from samplemorph.canonicalizers.linear_axis import onto_linear_axis
from samplemorph.images import AnalysisSpectrogram

GRIFFIN_LIM_ITERATIONS: Final[int] = 32


class GriffinLimVocoder:
    """Estimates the phase a magnitude spectrogram lost, by Griffin and Lim's iterative method.

    Every geometry is first read onto the linear Fourier grid its analysis window defines, and one
    inversion runs from there, so the audible difference between two frequency axes comes from the
    axes rather than from two different synthesis routes.
    """

    def __init__(self, *, iterations: int = GRIFFIN_LIM_ITERATIONS) -> None:
        self._iterations = iterations

    def synthesize(self, spectrogram: AnalysisSpectrogram) -> NDArray[np.float64]:
        linear = onto_linear_axis(spectrogram.magnitude, geometry=spectrogram.geometry)
        waveform: NDArray[np.float64] = librosa.griffinlim(
            linear,
            n_iter=self._iterations,
            hop_length=spectrogram.geometry.hop_length,
            n_fft=spectrogram.geometry.fft_length,
            length=spectrogram.frame_count,
        )
        return waveform


class OraclePhaseVocoder:
    """Reuses a known waveform's own phase, reporting what a perfect phase estimate would leave.

    This is a measuring instrument rather than a way to make new sound: it needs the very signal a
    vocoder is supposed to be recovering. Comparing it against `GriffinLimVocoder` separates what
    the frequency axis and the grid throw away from what the phase estimate throws away, which is
    what decides whether a better vocoder is worth training.
    """

    def __init__(self, reference: NDArray[np.float64]) -> None:
        self._reference = reference

    def synthesize(self, spectrogram: AnalysisSpectrogram) -> NDArray[np.float64]:
        geometry = spectrogram.geometry
        linear = onto_linear_axis(spectrogram.magnitude, geometry=geometry)
        reference = librosa.stft(self._reference, n_fft=geometry.fft_length, hop_length=geometry.hop_length)
        frames = min(linear.shape[1], reference.shape[1])
        phase = np.exp(1j * np.angle(reference[:, :frames]))
        waveform: NDArray[np.float64] = librosa.istft(
            linear[:, :frames] * phase,
            hop_length=geometry.hop_length,
            n_fft=geometry.fft_length,
            length=spectrogram.frame_count,
        )
        return waveform
