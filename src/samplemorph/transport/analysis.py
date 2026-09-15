from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.ndimage import convolve1d

from samplecore.auditory.strikes import main_onset
from samplemorph.canonicalizers.common import PreparedMono, analysis_transform
from samplemorph.geometry import LogFrequencyGeometry
from samplemorph.transport.settings import TransportSettings


@dataclass(frozen=True)
class TransportAnalysis:
    """One sound's Gaussian analysis in the form a transport reads it.

    `energy` is the squared magnitude, bins by frames. `outline` is that energy smoothed over
    neighboring frames and bins, read only to cut a spectrum into groups, so the cuts hold still
    from frame to frame while every move carries the raw energy. `frame_energy` is each frame's
    total, `silent_shape` the sound's mean spectrum with unit sum, `onset_sample` where its main
    strike begins, and `sample_count` the length the analysis describes.
    """

    energy: NDArray[np.float32]
    outline: NDArray[np.float32]
    frame_energy: NDArray[np.float32]
    silent_shape: NDArray[np.float32]
    onset_sample: int
    sample_count: int

    @property
    def frame_count(self) -> int:
        return int(self.energy.shape[1])

    @property
    def peak_frame_energy(self) -> float:
        return float(self.frame_energy.max())

    @property
    def nbytes(self) -> int:
        return int(self.energy.nbytes + self.outline.nbytes + self.frame_energy.nbytes + self.silent_shape.nbytes)


def analyze(
    mono: PreparedMono, *, rate_hz: float, geometry: LogFrequencyGeometry, settings: TransportSettings
) -> TransportAnalysis:
    """Analyze a prepared waveform heard at `rate_hz` into what a transport reads.

    The onset is read at the heard rate, since a strike is a matter of milliseconds as heard.
    """
    energy = (np.abs(analysis_transform(mono, geometry=geometry)) ** 2).astype(np.float32)
    return TransportAnalysis(
        energy=energy,
        outline=_outline(energy, settings=settings),
        frame_energy=energy.sum(axis=0),
        silent_shape=_mean_shape(energy),
        onset_sample=main_onset(mono, sample_rate_hz=int(round(rate_hz))),
        sample_count=int(mono.shape[0]),
    )


def _outline(energy: NDArray[np.float32], *, settings: TransportSettings) -> NDArray[np.float32]:
    across_frames = convolve1d(energy, _triangle(settings.outline_frame_reach), axis=1, mode="constant")
    outline: NDArray[np.float32] = convolve1d(
        across_frames, _triangle(settings.outline_bin_reach), axis=0, mode="constant"
    )
    return outline


def _triangle(reach: int) -> NDArray[np.float32]:
    weights = (reach + 1 - np.abs(np.arange(-reach, reach + 1))).astype(np.float32)
    return weights / weights.sum()


def _mean_shape(energy: NDArray[np.float32]) -> NDArray[np.float32]:
    """The mean spectrum with unit sum; a silent sound's shape spreads evenly over every bin."""
    totals = energy.sum(axis=1, dtype=np.float64)
    total = float(totals.sum())
    if total <= 0.0:
        return np.full(energy.shape[0], 1.0 / energy.shape[0], dtype=np.float32)
    return (totals / total).astype(np.float32)
