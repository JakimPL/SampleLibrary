from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Final, Protocol

import librosa
import numpy as np
from trackmod.core.samples.depth import BitDepth

from samplecore.waveform import requantized, resample_by_semitones
from samplemorph.canonicalizers.common import SHORT_SIGNAL_WARNING, PreparedMono
from samplemorph.measurement.pitch.trials import TrialKind

RETUNING_INTERVALS_SEMITONES: Final[tuple[float, ...]] = (
    -17.0,
    -12.0,
    -7.0,
    -5.0,
    -3.0,
    -2.0,
    -1.0,
    -0.5,
    0.5,
    1.0,
    2.0,
    3.0,
    5.0,
    7.0,
    12.0,
    17.0,
)
STRETCH_FACTORS: Final[tuple[float, ...]] = (0.5, 2.0)
LEVEL_CHANGE_DB: Final[float] = -30.0
REQUANTIZED_DEPTH: Final[BitDepth] = BitDepth.EIGHT
KEPT_PITCH_SEMITONES: Final[float] = 0.0
# librosa 1.0 passes its own deprecated arguments on to the phase vocoder, which warns and ignores them.
DEPRECATED_ARGUMENT_WARNING: Final[str] = r"The `\w+` parameter is deprecated"


class SoundChange(Protocol):
    """One way a held-out sample is changed before it is read, and how far the change moves its pitch."""

    @property
    def name(self) -> str: ...

    @property
    def kind(self) -> TrialKind: ...

    @property
    def expected_semitones(self) -> float: ...

    def __call__(self, mono: PreparedMono) -> PreparedMono: ...


class PitchKeepingMorph(Protocol):
    """A morph whose middle keeps the first sound's pitch content, which a pitch reading must find unmoved."""

    @property
    def name(self) -> str: ...

    def middle(self, first: PreparedMono, second: PreparedMono) -> PreparedMono: ...


@dataclass(frozen=True)
class Retuning:
    """The sample read at a playback rate `semitones` away, which moves its pitch by exactly that."""

    semitones: float

    @property
    def name(self) -> str:
        return f"retuned{self.semitones:+g}"

    @property
    def kind(self) -> TrialKind:
        return TrialKind.RETUNING

    @property
    def expected_semitones(self) -> float:
        return self.semitones

    def __call__(self, mono: PreparedMono) -> PreparedMono:
        return PreparedMono(resample_by_semitones(mono, semitones=self.semitones))


@dataclass(frozen=True)
class TimeStretch:
    """The sample made `duration_factor` times as long by a phase vocoder, at its own pitch."""

    duration_factor: float

    @property
    def name(self) -> str:
        return f"stretched-x{self.duration_factor:g}"

    @property
    def kind(self) -> TrialKind:
        return TrialKind.INVARIANCE

    @property
    def expected_semitones(self) -> float:
        return KEPT_PITCH_SEMITONES

    def __call__(self, mono: PreparedMono) -> PreparedMono:
        with warnings.catch_warnings():
            # librosa warns about a signal shorter than one transform and stretches it regardless.
            warnings.filterwarnings("ignore", message=SHORT_SIGNAL_WARNING, category=UserWarning)
            warnings.filterwarnings("ignore", message=DEPRECATED_ARGUMENT_WARNING, category=FutureWarning)
            stretched = librosa.effects.time_stretch(mono, rate=1.0 / self.duration_factor)
        return PreparedMono(stretched.astype(np.float64))


@dataclass(frozen=True)
class LevelChange:
    """The sample played `decibels` louder, a quieter one for a negative number."""

    decibels: float

    @property
    def name(self) -> str:
        return f"level{self.decibels:+g}db"

    @property
    def kind(self) -> TrialKind:
        return TrialKind.INVARIANCE

    @property
    def expected_semitones(self) -> float:
        return KEPT_PITCH_SEMITONES

    def __call__(self, mono: PreparedMono) -> PreparedMono:
        return PreparedMono(mono * 10.0 ** (self.decibels / 20.0))


@dataclass(frozen=True)
class Requantization:
    """The sample stored at `depth`, rounded the way the library stores a tracker's samples."""

    depth: BitDepth

    @property
    def name(self) -> str:
        return f"requantized-{self.depth.value}-bit"

    @property
    def kind(self) -> TrialKind:
        return TrialKind.INVARIANCE

    @property
    def expected_semitones(self) -> float:
        return KEPT_PITCH_SEMITONES

    def __call__(self, mono: PreparedMono) -> PreparedMono:
        return PreparedMono(requantized(mono, depth=self.depth))


def default_changes() -> tuple[SoundChange, ...]:
    """Every true retuning a reading asks about, then the changes that keep the pitch: stretched, quieter, requantized."""
    return (
        *(Retuning(semitones=semitones) for semitones in RETUNING_INTERVALS_SEMITONES),
        *(TimeStretch(duration_factor=factor) for factor in STRETCH_FACTORS),
        LevelChange(decibels=LEVEL_CHANGE_DB),
        Requantization(depth=REQUANTIZED_DEPTH),
    )
