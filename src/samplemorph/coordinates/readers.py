from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Protocol

import librosa
import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, Field, JsonValue

from samplecore.models.base import FROZEN
from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.canonicalizers.common import PreparedMono, harmonic_sum, to_magnitudes
from samplemorph.coordinates.frames import FrameAnalysis, constant_q_frames, frame_analysis
from samplemorph.geometry import MINIMUM_FREQUENCY_HZ, semitones_from_reference

SUBHARMONIC_READER_NAME: Final[str] = "subharmonic"
PYIN_READER_NAME: Final[str] = "pyin"
PEAK_REACH_SEMITONES: Final[float] = 1.0
BACKGROUND_REACH_SEMITONES: Final[float] = 12.0
# C8, the top of a piano, which also holds an 8-bit sample's pitch read in the nominal frame.
PYIN_HIGHEST_HZ: Final[float] = 4186.0
# Two periods of the lowest frame bin fit in half of it at the nominal rate, which pYIN's search needs.
PYIN_FRAME_LENGTH: Final[int] = 4096
# Read off 20 held-out samples, each at 16 true retunings: above 0.5 the subharmonic reader followed
# 97% of them within half a semitone, and every drum-like sample read under 0.4.
SUBHARMONIC_TRUSTED_RELIABILITY: Final[float] = 0.5
# Where pYIN's top tercile began on the same reading, every retuning in it followed within half a semitone.
PYIN_TRUSTED_RELIABILITY: Final[float] = 0.5


@dataclass(frozen=True)
class PitchReading:
    """Where a sound's pitch sits and how far its reader trusts that.

    `semitones` counts from `REFERENCE_FREQUENCY_HZ` in the nominal frame, the rate every stored
    sample is read at, and `reliability` lies in ``[0, 1]``.
    """

    semitones: float
    reliability: float


class PitchReader(Protocol):
    """A reader a route asks for a sound's pitch, under a name, with the reliability its readings are trusted from.

    `description` names everything the reader reads with, so a route whose reader changes renders
    under another fingerprint.
    """

    @property
    def name(self) -> str: ...

    @property
    def trusted_reliability(self) -> float: ...

    def read(self, mono: PreparedMono) -> PitchReading | None: ...

    def description(self) -> dict[str, JsonValue]: ...


class SubharmonicReader(BaseModel):
    """Hermes's subharmonic summation over a sound's constant-Q frames, refined between bins.

    It reads the frames a pitch head reads, so the two differ in the reader alone. The profile is
    the frames' mean read back as linear magnitude, as `fundamental_band` reads a grid, and every
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

    def description(self) -> dict[str, JsonValue]:
        return {"reader": self.name, **self.model_dump(mode="json")}

    def read(self, mono: PreparedMono) -> PitchReading | None:
        """The sound's pitch, or None for a sound with no frame that sounds."""
        frames = constant_q_frames(mono, analysis=self.analysis)
        if frames.shape[0] == 0:
            return None
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


class PyinReader(BaseModel):
    """Probabilistic YIN (Mauch and Dixon, 2014) over the waveform, the median of its voiced frames.

    The search spans `lowest_hz` to `highest_hz` at the nominal rate. The reliability is the share of
    frames pYIN calls voiced times their mean voicing probability, so a held note reads near one, a
    struck one by how long it rings, and a noise near zero.
    """

    model_config = FROZEN

    analysis_rate_hz: int = Field(gt=0)
    lowest_hz: float = Field(gt=0.0)
    highest_hz: float = Field(gt=0.0)
    frame_length: int = Field(gt=0)
    trusted_reliability: float = Field(ge=0.0, le=1.0)

    @property
    def name(self) -> str:
        return PYIN_READER_NAME

    def description(self) -> dict[str, JsonValue]:
        return {"reader": self.name, **self.model_dump(mode="json")}

    def read(self, mono: PreparedMono) -> PitchReading | None:
        """The sound's pitch, or None for a sound with no voiced frame."""
        frequencies, voiced, probabilities = librosa.pyin(
            mono.astype(np.float32),
            fmin=self.lowest_hz,
            fmax=self.highest_hz,
            sr=self.analysis_rate_hz,
            frame_length=self.frame_length,
        )
        if not voiced.any():
            return None
        return PitchReading(
            semitones=float(np.median([semitones_from_reference(float(hertz)) for hertz in frequencies[voiced]])),
            reliability=float(voiced.mean() * probabilities[voiced].mean()),
        )


def subharmonic_reader() -> SubharmonicReader:
    """The subharmonic reader on the frames a pitch head reads."""
    return SubharmonicReader(analysis=frame_analysis(), trusted_reliability=SUBHARMONIC_TRUSTED_RELIABILITY)


def pyin_reader() -> PyinReader:
    """pYIN at the nominal rate, from the lowest frame bin to the top of a piano."""
    return PyinReader(
        analysis_rate_hz=NOMINAL_WAV_RATE,
        lowest_hz=MINIMUM_FREQUENCY_HZ,
        highest_hz=PYIN_HIGHEST_HZ,
        frame_length=PYIN_FRAME_LENGTH,
        trusted_reliability=PYIN_TRUSTED_RELIABILITY,
    )


CLASSICAL_READERS: Final[dict[str, Callable[[], PitchReader]]] = {
    SUBHARMONIC_READER_NAME: subharmonic_reader,
    PYIN_READER_NAME: pyin_reader,
}


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
