from __future__ import annotations

from enum import StrEnum, unique
from typing import Final

WITHIN_SEMITONES: Final[float] = 0.5
JUMP_TOLERANCE_SEMITONES: Final[float] = 1.0
OCTAVE_JUMPS_SEMITONES: Final[tuple[float, ...]] = (12.0, 24.0, 36.0)
# The intervals a reader lands on when it takes the third harmonic or a subharmonic of it for the
# fundamental: 4/3, 3/2, 8/3, 3, 16/3 and 6, each within its octave.
FIFTH_JUMPS_SEMITONES: Final[tuple[float, ...]] = (5.0, 7.0, 17.0, 19.0, 29.0, 31.0)


@unique
class Residual(StrEnum):
    """What a reading's error amounts to.

    `WITHIN` lies within half a semitone of the truth. `OCTAVE` lies an octave or two off and
    `FIFTH` on another interval of the harmonic series, the errors a reader makes when it takes a
    harmonic or a subharmonic for the fundamental. `OFF` is anything else.
    """

    WITHIN = "within"
    OCTAVE = "octave"
    FIFTH = "fifth"
    OFF = "off"


def residual_of(error_semitones: float) -> Residual:
    """The kind of error a reading made, from how far it lies from the truth in semitones."""
    distance = abs(error_semitones)
    if distance <= WITHIN_SEMITONES:
        return Residual.WITHIN
    if _near_any(distance, OCTAVE_JUMPS_SEMITONES):
        return Residual.OCTAVE
    if _near_any(distance, FIFTH_JUMPS_SEMITONES):
        return Residual.FIFTH
    return Residual.OFF


def _near_any(distance: float, jumps: tuple[float, ...]) -> bool:
    return any(abs(distance - jump) <= JUMP_TOLERANCE_SEMITONES for jump in jumps)
