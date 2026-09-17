from __future__ import annotations

from enum import StrEnum, unique
from typing import Final

from pydantic import BaseModel, Field

from samplecore.models.base import FROZEN
from samplemorph.transport.morph import FIRST_END_WEIGHT, SECOND_END_WEIGHT

DEFAULT_COEFFICIENT_COUNT: Final[int] = 40
DEFAULT_FLOOR_DB: Final[float] = 80.0


@unique
class Excitation(StrEnum):
    """Whose excitation sounds under the moving envelope.

    `FIRST` keeps the first sound's along the whole path and `SECOND` the second's, so every point
    holds one sound's pitch content, and the far end is that content under the other sound's
    envelope. `BOTH` crossfades the two excitations with the weight, so both pitch contents sound
    in the middle while the envelope moves as one.
    """

    FIRST = "first"
    SECOND = "second"
    BOTH = "both"


DEFAULT_EXCITATION: Final[Excitation] = Excitation.FIRST


@unique
class Timeline(StrEnum):
    """Whose course through time a morph is heard on.

    `MORPHED` reads both sounds along a course between theirs, so a point lasts between the two
    lengths and its attack falls between the two attacks. `FIRST` holds the first sound's course, so
    every point lasts exactly as long as that sound and strikes where it strikes, with the second
    sound read along it; `SECOND` holds the second sound's the same way.

    A held course is what lets a morph keep one length from end to end, which is what an instrument
    playing the path a note at a time asks of it.
    """

    MORPHED = "morphed"
    FIRST = "first"
    SECOND = "second"

    def weight_at(self, morph_weight: float) -> float:
        """The weight the time map is built at while the morph itself stands at `morph_weight`."""
        match self:
            case Timeline.MORPHED:
                return morph_weight
            case Timeline.FIRST:
                return FIRST_END_WEIGHT
            case Timeline.SECOND:
                return SECOND_END_WEIGHT


DEFAULT_TIMELINE: Final[Timeline] = Timeline.MORPHED


class EnvelopeSettings(BaseModel):
    """Every constant an envelope morph reads, so a rendered file can name the settings it took.

    A spectrum's envelope is the shape its loudness over frequency takes when only its first
    `coefficient_count` cosines are kept, read down to `floor_db` under the loudest bin of the
    sound, `excitation` says whose excitation sounds under the envelope along the path, and
    `timeline` says whose course through time the path is heard on.
    """

    model_config = FROZEN

    coefficient_count: int = Field(default=DEFAULT_COEFFICIENT_COUNT, ge=1)
    floor_db: float = Field(default=DEFAULT_FLOOR_DB, gt=0.0)
    excitation: Excitation = DEFAULT_EXCITATION
    timeline: Timeline = DEFAULT_TIMELINE
