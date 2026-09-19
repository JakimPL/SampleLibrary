from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplecore.auditory.sound_type import SoundType, sound_type_reading
from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.geometry import SEMITONES_PER_OCTAVE
from samplemorph.measurement.pitch.reader import PitchReader

MINIMUM_PITCH_INTERVAL_SEMITONES: Final[float] = 1.0


@dataclass(frozen=True)
class PitchPath:
    """The pitch each point of a path is heard at, in semitones, beside the weight it stands at, ends first and last.

    A morph between two notes glides: every point lies on the straight line between the ends, and
    the pitch moves by a small step from one weight to the next. A morph that holds one note and
    then switches to the other lies off the line and moves in one step.
    """

    weights: tuple[float, ...]
    semitones: tuple[float, ...]

    def deviation_semitones(self, index: int) -> float:
        """How far one point's pitch lies from the straight line between the ends' pitches."""
        weight = self.weights[index]
        return self.semitones[index] - ((1.0 - weight) * self.semitones[0] + weight * self.semitones[-1])

    @property
    def is_read(self) -> bool:
        """Whether every point sounds a pitch the reader found."""
        return bool(np.all(np.isfinite(self.semitones)))

    @property
    def largest_deviation_semitones(self) -> float:
        """The farthest any point lies from the line, not a number when a point sounds no pitch."""
        if not self.is_read:
            return float("nan")
        return max(abs(self.deviation_semitones(index)) for index in range(len(self.weights)))

    @property
    def jump_share(self) -> float:
        """The largest step between neighboring points over the whole span the path covers.

        A switch reads one and a glide over `n` even steps reads `1/n`. Ends heard at one pitch
        span nothing, and a path with a point that sounds no pitch has no steps to read; the share
        is not a number on either.
        """
        span = max(self.semitones) - min(self.semitones)
        if not self.is_read or span <= 0.0:
            return float("nan")
        return float(np.abs(np.diff(self.semitones)).max()) / span


def heard_pitch(waveform: NDArray[np.float64], *, rate_hz: float, reader: PitchReader) -> float:
    """Where a waveform played at `rate_hz` sounds, in semitones from the reference frequency, or not a number where `reader` finds no pitch.

    The reader reads frames at the store's nominal rate, so the rate the waveform is played at moves
    the reading by the interval between the two.
    """
    reading = reader.read(prepare_mono(waveform))
    if reading is None:
        return float("nan")
    return reading.semitones + SEMITONES_PER_OCTAVE * float(np.log2(rate_hz / NOMINAL_WAV_RATE))


def is_pitched_pair(
    first: NDArray[np.float64], second: NDArray[np.float64], *, rate_hz: float, reader: PitchReader
) -> bool:
    """Whether two sounds played at `rate_hz` both read tonal and lie at least `MINIMUM_PITCH_INTERVAL_SEMITONES` apart.

    Such a pair is the one a listener hears glide: both carry a harmonic series for the reading to
    follow, across an interval of at least a semitone.
    """
    sample_rate_hz = int(round(rate_hz))
    both_tonal = all(
        sound_type_reading(sound, sample_rate_hz=sample_rate_hz).sound_type is SoundType.TONAL
        for sound in (first, second)
    )
    if not both_tonal:
        return False
    interval = heard_pitch(first, rate_hz=rate_hz, reader=reader) - heard_pitch(second, rate_hz=rate_hz, reader=reader)
    return abs(interval) >= MINIMUM_PITCH_INTERVAL_SEMITONES
