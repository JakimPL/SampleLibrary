from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique

from samplemorph.measurement.pitch.reader import ReadPitch
from samplemorph.measurement.pitch.residuals import Residual, residual_of


@unique
class TrialKind(StrEnum):
    """What a trial asks of a reader, and what it is checked against.

    `RETUNING` reads a held-out sample and a true retuning of it, which must differ by the
    retuning. `INVARIANCE` reads it and a change that keeps its pitch, which must read alike.
    `CONSENSUS` reads a held-out sample both referees place within half a semitone of each other,
    which must read where they do. `FAMILY` reads a synthetic tone, which must read at its
    fundamental. `PAIR` reads two synthetic tones of different timbres, which must differ by their
    interval.
    """

    RETUNING = "retuning"
    INVARIANCE = "invariance"
    CONSENSUS = "consensus"
    FAMILY = "family"
    PAIR = "pair"


@dataclass(frozen=True)
class SampleContext:
    """Where a held-out sample falls: its sound type, its duration tercile, and the octave its referees agree on."""

    sound_type: str
    duration: str
    register: str


@dataclass(frozen=True)
class Trial:
    """One reader's answer to one question with a known answer: a pitch, or an interval between two readings.

    `found_semitones` is None when the reader found no pitch in a sound the trial reads, which
    counts against it as a reading it did not make. `reliability` is the reader's own trust in the
    reading, the lower of the two for an interval, and 0 for a reading not made. A trial on a
    held-out sample carries the sample's `context`; a synthetic one carries none.
    """

    reader: str
    kind: TrialKind
    group: str
    source: str
    expected_semitones: float
    found_semitones: float | None
    reliability: float
    context: SampleContext | None

    @property
    def error_semitones(self) -> float | None:
        return None if self.found_semitones is None else self.found_semitones - self.expected_semitones

    @property
    def residual(self) -> Residual | None:
        error = self.error_semitones
        return None if error is None else residual_of(error)


@dataclass(frozen=True)
class Question:
    """What one trial asks, before any reader answers it."""

    kind: TrialKind
    group: str
    source: str
    expected_semitones: float
    context: SampleContext | None


def pitch_trial(question: Question, *, reader: str, reading: ReadPitch | None) -> Trial:
    """A trial of where one reading places a sound, against the pitch the question expects."""
    return Trial(
        reader=reader,
        kind=question.kind,
        group=question.group,
        source=question.source,
        expected_semitones=question.expected_semitones,
        found_semitones=None if reading is None else reading.semitones,
        reliability=0.0 if reading is None else reading.reliability,
        context=question.context,
    )


def interval_trial(question: Question, *, reader: str, reference: ReadPitch | None, probe: ReadPitch | None) -> Trial:
    """A trial of how far one reading lies from another, against the interval the question expects."""
    if reference is None or probe is None:
        found, reliability = None, 0.0
    else:
        found, reliability = probe.semitones - reference.semitones, min(reference.reliability, probe.reliability)
    return Trial(
        reader=reader,
        kind=question.kind,
        group=question.group,
        source=question.source,
        expected_semitones=question.expected_semitones,
        found_semitones=found,
        reliability=reliability,
        context=question.context,
    )
