from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from samplecore.labeling.labels import SampleLabel, written_paths


@dataclass(frozen=True)
class SoundKind:
    """A kind of sound pairs are drawn from: the name it goes by, the labels that name it, and whether it is struck."""

    name: str
    labels: tuple[str, ...]
    percussive: bool

    def is_named_by(self, label: str) -> bool:
        """Whether a label names this kind: one of its tags, or anything under one in the label hierarchy."""
        closure = SampleLabel.parse(label).closure
        return any(path in closure for own in self.labels for path in written_paths(own))


BASS_DRUM: Final[SoundKind] = SoundKind(name="bass-drum", labels=("BASS DRUM",), percussive=True)
SNARE: Final[SoundKind] = SoundKind(name="snare", labels=("SNARE",), percussive=True)
HI_HAT: Final[SoundKind] = SoundKind(name="hi-hat", labels=("HI-HAT",), percussive=True)
BASS: Final[SoundKind] = SoundKind(name="bass", labels=("BASS",), percussive=False)
LEAD: Final[SoundKind] = SoundKind(name="lead", labels=("SYNTH: LEAD",), percussive=False)
PAD: Final[SoundKind] = SoundKind(name="pad", labels=("SYNTH: PAD",), percussive=False)
PIANO: Final[SoundKind] = SoundKind(name="piano", labels=("PIANO",), percussive=False)
CHORD: Final[SoundKind] = SoundKind(name="chord", labels=("CHORD",), percussive=False)

PERCUSSIVE_KINDS: Final[tuple[SoundKind, ...]] = (BASS_DRUM, SNARE, HI_HAT)
TONAL_KINDS: Final[tuple[SoundKind, ...]] = (BASS, LEAD, PAD, PIANO, CHORD)
SUSTAINED_KINDS: Final[tuple[SoundKind, ...]] = (PAD, CHORD)
SAME_KINDS: Final[tuple[SoundKind, ...]] = (*PERCUSSIVE_KINDS, *TONAL_KINDS)
CROSS_KINDS: Final[tuple[tuple[SoundKind, SoundKind], ...]] = (
    (BASS_DRUM, SNARE),
    (SNARE, HI_HAT),
    (BASS_DRUM, BASS),
    (BASS, LEAD),
    (PIANO, PAD),
    (LEAD, CHORD),
)
