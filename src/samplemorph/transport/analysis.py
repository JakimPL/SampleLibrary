from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from samplecore.auditory.strikes import main_onset
from samplemorph.canonicalizers.common import PreparedMono, analysis_transform
from samplemorph.geometry import LogFrequencyGeometry
from samplemorph.transport.frame_reading import read_frames
from samplemorph.transport.settings import TransportSettings


@dataclass(frozen=True)
class TransportAnalysis:
    """One sound's Gaussian analysis in the form the envelope route reads it.

    `energy` is the squared magnitude, bins by frames. `frame_energy` is each frame's total,
    `onset_sample` where the sound's main strike begins, and `sample_count` the length the analysis
    describes.
    """

    energy: NDArray[np.float32]
    frame_energy: NDArray[np.float32]
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
        return int(self.energy.nbytes + self.frame_energy.nbytes)


def analyze(mono: PreparedMono, *, rate_hz: float, geometry: LogFrequencyGeometry) -> TransportAnalysis:
    """Analyze a prepared waveform heard at `rate_hz` into what the envelope route reads.

    The onset is read at the heard rate, since a strike is a matter of milliseconds as heard.
    """
    energy = (np.abs(analysis_transform(mono, geometry=geometry)) ** 2).astype(np.float32)
    return TransportAnalysis(
        energy=energy,
        frame_energy=energy.sum(axis=0),
        onset_sample=main_onset(mono, sample_rate_hz=int(round(rate_hz))),
        sample_count=int(mono.shape[0]),
    )


def read_magnitude(
    analysis: TransportAnalysis,
    *,
    positions: NDArray[np.float64],
    rates: NDArray[np.float64],
    settings: TransportSettings,
) -> NDArray[np.float32]:
    """A sound's amplitudes where a time map points: its energy read along the map, rooted.

    Shapes: `positions` and `rates` are ``(output frames,)`` and the result ``(bins, output frames)``.
    """
    energy = read_frames(
        analysis.energy, positions=positions, rates=rates, maximum_half_width=settings.maximum_reading_half_width
    )
    magnitude: NDArray[np.float32] = np.sqrt(np.maximum(energy, 0.0)).astype(np.float32)
    return magnitude
