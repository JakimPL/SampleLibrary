from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, Field, JsonValue

from samplecore.models.base import FROZEN
from samplemorph.canonicalizers.common import PreparedMono, harmonic_sum, to_magnitudes
from samplemorph.coordinates.frames import FrameAnalysis, constant_q_frames, frame_analysis
from samplemorph.geometry import semitones_from_reference

SUBHARMONIC_READER_NAME: Final[str] = "subharmonic"
PEAK_REACH_SEMITONES: Final[float] = 1.0
BACKGROUND_REACH_SEMITONES: Final[float] = 12.0
# Read off 20 held-out samples, each at 16 true retunings: above 0.5 the subharmonic reader followed
# 97% of them within half a semitone, and every drum-like sample read under 0.4.
SUBHARMONIC_TRUSTED_RELIABILITY: Final[float] = 0.5


@dataclass(frozen=True)
class PitchReading:
    """Where a sound's pitch sits and how far its reader trusts that.

    `semitones` counts from `REFERENCE_FREQUENCY_HZ` in the nominal frame, the rate every stored
    sample is read at, and `reliability` lies in ``[0, 1]``.
    """

    semitones: float
    reliability: float


class SubharmonicReader(BaseModel):
    """Hermes's subharmonic summation over a sound's constant-Q frames, refined between bins.

    The profile is the frames' mean read back as linear magnitude, and every
    bin is scored as a fundamental by `harmonic_sum`. The best bin is refined by the parabola through
    the logarithms of its score and its neighbors', which is exact for a Gaussian peak. The
    reliability is how far the peak stands over the scores within an octave of it: one minus their
    median over the peak, the bins within a semitone of the peak set aside, so a line spectrum reads
    near one and a flat noise near zero.
    """

    model_config = FROZEN

    analysis: FrameAnalysis
    trusted_reliability: float = Field(ge=0.0, le=1.0)

    @property
    def name(self) -> str:
        return SUBHARMONIC_READER_NAME

    def describe(self) -> dict[str, JsonValue]:
        return {"reader": self.name, **self.model_dump(mode="json")}

    def read(self, mono: PreparedMono) -> PitchReading | None:
        """The sound's pitch, or None for a sound with no frame that sounds."""
        frames = constant_q_frames(mono, analysis=self.analysis)
        if frames.shape[0] == 0:
            return None
        return self.read_frames(frames)

    def read_frames(self, frames: NDArray[np.float32]) -> PitchReading:
        """The pitch a sound's kept frames sound. Shape: `frames` is ``(frames, bands)``."""
        profile = to_magnitudes(
            frames.mean(axis=0).astype(np.float64), dynamic_range_db=self.analysis.frame_range_db, log_gain=0.0
        )
        scores = harmonic_sum(profile, frequencies=self.analysis.band_frequencies_hz())
        peak = int(np.argmax(scores))
        band = peak + parabolic_offset(np.log(scores), peak=peak)
        frequency_hz = self.analysis.minimum_frequency_hz * 2.0 ** (band / self.analysis.bins_per_octave)
        return PitchReading(
            semitones=semitones_from_reference(frequency_hz),
            reliability=_peak_contrast(scores, peak=peak, bins_per_semitone=self.analysis.bins_per_semitone),
        )


def subharmonic_reader() -> SubharmonicReader:
    """The subharmonic reader on the frames a pitch head reads."""
    return SubharmonicReader(analysis=frame_analysis(), trusted_reliability=SUBHARMONIC_TRUSTED_RELIABILITY)


def parabolic_offset(values: NDArray[np.float64], *, peak: int) -> float:
    """Where the parabola through a peak and its two neighbors tops out, in bins from the peak, within half a bin.

    A peak on either edge, or one flat against a neighbor, stays on its bin.
    """
    if peak in (0, values.size - 1):
        return 0.0
    left, center, right = float(values[peak - 1]), float(values[peak]), float(values[peak + 1])
    curvature = left - 2.0 * center + right
    if curvature >= 0.0:
        return 0.0
    return float(np.clip(0.5 * (left - right) / curvature, -0.5, 0.5))


def _peak_contrast(scores: NDArray[np.float64], *, peak: int, bins_per_semitone: float) -> float:
    """One minus the median score within an octave of the peak, the peak's own semitone set aside, over the peak's score."""
    distance = np.abs(np.arange(scores.size) - peak)
    around = (distance > PEAK_REACH_SEMITONES * bins_per_semitone) & (
        distance <= BACKGROUND_REACH_SEMITONES * bins_per_semitone
    )
    return float(np.clip(1.0 - np.median(scores[around]) / scores[peak], 0.0, 1.0))
