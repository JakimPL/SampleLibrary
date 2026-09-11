from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import librosa
import numpy as np
from numpy.typing import NDArray

from samplemorph.canonicalizers import Canonicalizer
from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.canonicalizers.linear_axis import onto_linear_axis
from samplemorph.geometry import Geometry, analysis_taper

SILENT_LEVEL: Final[float] = 1e-8


@dataclass(frozen=True)
class PipelineAnalysis:
    """One sound as the pipeline hands it to a vocoder, beside the analysis it was read from.

    `magnitude` is what a vocoder meets: the sound carried through the canonical grid and read
    back onto the linear Fourier axis, smoothed by everything that grid discards. `analysis` is
    the short-time Fourier transform of the same prepared waveform under the same taper, so a
    frame of one and a frame of the other describe the same moment: its angle is the phase that
    magnitude belongs with, and its modulus the fine structure the grid removed.
    """

    magnitude: NDArray[np.float64]
    analysis: NDArray[np.complex128]

    @property
    def frame_count(self) -> int:
        return int(self.magnitude.shape[1])


def analyze_through_pipeline(
    waveform: NDArray[np.float64], *, canonicalizer: Canonicalizer, geometry: Geometry
) -> PipelineAnalysis | None:
    """Carry one waveform through the pipeline and pair the result with the analysis it came from.

    Both sides are read from the same prepared waveform on the same analysis window. Preparing it
    here rather than leaving each side to do its own is what keeps them the same waveform: a
    canonicalizer centers what it is given, and an analysis of an uncentered reading would belong
    to a slightly different signal. A silent waveform returns nothing, since it carries nothing to
    learn from.
    """
    mono = prepare_mono(waveform)
    if float(np.abs(mono).max()) < SILENT_LEVEL:
        return None

    spectrogram = canonicalizer.restore(canonicalizer.canonicalize(mono))
    magnitude = onto_linear_axis(spectrogram.magnitude, geometry=geometry)
    analysis = librosa.stft(
        mono, n_fft=geometry.fft_length, hop_length=geometry.hop_length, window=analysis_taper(geometry)
    )
    frames = min(magnitude.shape[1], analysis.shape[1])
    if frames < 1:
        return None

    return PipelineAnalysis(magnitude=magnitude[:, :frames], analysis=analysis[:, :frames])
