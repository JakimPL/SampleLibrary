from __future__ import annotations

from enum import StrEnum, unique


@unique
class SampleCategory(StrEnum):
    """A coarse instrument-role classification for a sample, guessed from its occurrence names."""

    KICK = "kick"
    SNARE = "snare"
    CLAP = "clap"
    HI_HAT = "hi_hat"
    CYMBAL = "cymbal"
    PERCUSSION = "percussion"
    BASS = "bass"
    LEAD = "lead"
    PAD = "pad"
    PLUCK = "pluck"
    VOCAL = "vocal"
    FX = "fx"
    LOOP = "loop"
    UNCATEGORIZED = "uncategorized"
