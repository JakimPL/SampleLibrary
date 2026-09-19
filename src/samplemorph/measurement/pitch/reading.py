from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Final, Protocol

import numpy as np

from samplecore.auditory.sound_type import sound_type_reading
from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplecore.storage.sample_audio import SampleAudio
from samplemorph.canonicalizers.common import PreparedMono, prepare_mono
from samplemorph.measurement.pitch.changes import KEPT_PITCH_SEMITONES, PitchKeepingMorph, SoundChange
from samplemorph.measurement.pitch.reader import PitchReader, ReadPitch
from samplemorph.measurement.pitch.trials import TrialKind

STORED_VARIANT: Final[str] = "stored"
SILENT_SOUND_TYPE: Final[str] = "silent"


class SyntheticSound(Protocol):
    """A synthetic sound rendered on demand under the name its readings carry."""

    @property
    def name(self) -> str: ...

    def render(self) -> PreparedMono: ...


@dataclass(frozen=True)
class Variant:
    """One way a held-out sample is read besides as stored: what the trial asks and how far the pitch should move."""

    name: str
    kind: TrialKind
    expected_semitones: float


@dataclass(frozen=True)
class DrawnSample:
    """A held-out sample to read, beside the sample its pitch-keeping morphs run toward."""

    sample_hash: str
    partner_hash: str


@dataclass(frozen=True)
class SampleReadings:
    """Every reader's reading of one held-out sample, as stored and under every variant, keyed by variant and reader.

    `sound_type` is the sample's `SoundType` value, or `SILENT_SOUND_TYPE` for a sample with no sound in it.
    """

    sample_hash: str
    seconds: float
    sound_type: str
    readings: Mapping[tuple[str, str], ReadPitch | None]


@dataclass(frozen=True)
class SyntheticReadings:
    """Every reader's reading of one synthetic sound, keyed by reader."""

    name: str
    readings: Mapping[str, ReadPitch | None]


def variants_of(changes: tuple[SoundChange, ...], morphs: tuple[PitchKeepingMorph, ...]) -> tuple[Variant, ...]:
    """What every change and every morph asks: a change moves the pitch as it states, and a morph's middle keeps it."""
    return (
        *(
            Variant(name=change.name, kind=change.kind, expected_semitones=change.expected_semitones)
            for change in changes
        ),
        *(
            Variant(name=morph.name, kind=TrialKind.INVARIANCE, expected_semitones=KEPT_PITCH_SEMITONES)
            for morph in morphs
        ),
    )


@dataclass(frozen=True)
class HeldOutReader:
    """Reads one held-out sample as stored, under every change and through every morph, with every reader.

    Built once and sent to every worker process. Each variant is made, read and let go before the
    next is made, so a long sample holds one variant's frames at a time.
    """

    audio: SampleAudio
    readers: tuple[PitchReader, ...]
    changes: tuple[SoundChange, ...]
    morphs: tuple[PitchKeepingMorph, ...]

    def __call__(self, drawn: DrawnSample) -> SampleReadings:
        mono = self._mono(drawn.sample_hash)
        return SampleReadings(
            sample_hash=drawn.sample_hash,
            seconds=len(mono) / NOMINAL_WAV_RATE,
            sound_type=_sound_type(mono),
            readings={
                (variant, reader.name): reader.read(sound)
                for variant, sound in self._variants(mono, partner_hash=drawn.partner_hash)
                for reader in self.readers
            },
        )

    def _variants(self, mono: PreparedMono, *, partner_hash: str) -> Iterator[tuple[str, PreparedMono]]:
        yield STORED_VARIANT, mono
        for change in self.changes:
            yield change.name, change(mono)
        if self.morphs:
            partner = self._mono(partner_hash)
            for morph in self.morphs:
                yield morph.name, morph.middle(mono, partner)

    def _mono(self, sample_hash: str) -> PreparedMono:
        return prepare_mono(self.audio.read_by_hash(sample_hash).pcm)


@dataclass(frozen=True)
class SyntheticReader:
    """Renders one synthetic sound and reads it with every reader; built once and sent to every worker process."""

    readers: tuple[PitchReader, ...]

    def __call__(self, sound: SyntheticSound) -> SyntheticReadings:
        mono = sound.render()
        return SyntheticReadings(name=sound.name, readings={reader.name: reader.read(mono) for reader in self.readers})


def _sound_type(mono: PreparedMono) -> str:
    if not np.any(mono):
        return SILENT_SOUND_TYPE
    return sound_type_reading(mono, sample_rate_hz=NOMINAL_WAV_RATE).sound_type.value
