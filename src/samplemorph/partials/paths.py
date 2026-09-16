from __future__ import annotations

from enum import StrEnum, unique
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.geometry import SEMITONES_PER_OCTAVE
from samplemorph.partials.tracks import CENTS_PER_OCTAVE

CENTS_PER_SEMITONE: Final[float] = CENTS_PER_OCTAVE / SEMITONES_PER_OCTAVE
HALFWAY: Final[float] = 0.5
STEP_TIE_MARGIN: Final[float] = 0.02


@unique
class PitchPath(StrEnum):
    """How a partial travels from one pitch to another.

    `GLIDE` moves evenly in pitch, so every point between two notes is a pitch of its own. `STEPPED`
    moves in whole semitones, a partial that has travelled half a step standing at the next one, so
    every point is a note a keyboard holds. `SWITCH` stays where it started and arrives at the halfway
    mark, which changes the chord in one step while everything else moves.
    """

    GLIDE = "glide"
    STEPPED = "stepped"
    SWITCH = "switch"


@unique
class TimbrePath(StrEnum):
    """How the loudness of a partial travels.

    `WITH_PARTIALS` carries each partial's own loudness along with it, which is exact at both ends.
    """

    WITH_PARTIALS = "with_partials"


@unique
class FadeLaw(StrEnum):
    """When a partial meeting nothing in the other sound fades.

    `LEVEL_PATH` fades it along the same level path a partial meeting silence takes, so it is still
    heard, softly, at the midpoint. `EARLY` has it gone by the midpoint, which leaves the middle
    standing on what the two sounds share and on the other sound's partials. `LATE` holds it to the
    midpoint and fades it over the second half.
    """

    LEVEL_PATH = "level_path"
    EARLY = "early"
    LATE = "late"


def pitch_between(
    first_cents: NDArray[np.float64], second_cents: NDArray[np.float64], *, weight: float, path: PitchPath
) -> NDArray[np.float64]:
    """Where a partial stands `weight` of the way from one pitch to another. Shapes: both arrays are ``(partials, frames)``."""
    match path:
        case PitchPath.GLIDE:
            return (1.0 - weight) * first_cents + weight * second_cents
        case PitchPath.STEPPED:
            travelled = weight * (second_cents - first_cents)
            steps = np.sign(travelled) * np.floor(np.abs(travelled) / CENTS_PER_SEMITONE + HALFWAY + STEP_TIE_MARGIN)
            return first_cents + steps * CENTS_PER_SEMITONE
        case PitchPath.SWITCH:
            return first_cents if weight < HALFWAY else second_cents


def fade_progress(*, weight: float, law: FadeLaw) -> float:
    """How far a partial meeting nothing has faded at `weight`, 0 where it stands full and 1 where it is gone."""
    match law:
        case FadeLaw.LEVEL_PATH:
            return weight
        case FadeLaw.EARLY:
            return min(weight / HALFWAY, 1.0)
        case FadeLaw.LATE:
            return max((weight - HALFWAY) / HALFWAY, 0.0)
