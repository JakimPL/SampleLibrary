from __future__ import annotations

from enum import StrEnum, unique
from typing import Final

from pydantic import BaseModel, Field

from samplecore.models.base import FROZEN

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


class EnvelopeSettings(BaseModel):
    """Every constant an envelope morph reads, so a rendered file can name the settings it took.

    A spectrum's envelope is the shape its loudness over frequency takes when only its first
    `coefficient_count` cosines are kept, read down to `floor_db` under the loudest bin of the
    sound, and `excitation` says whose excitation sounds under the envelope along the path.
    """

    model_config = FROZEN

    coefficient_count: int = Field(default=DEFAULT_COEFFICIENT_COUNT, ge=1)
    floor_db: float = Field(default=DEFAULT_FLOOR_DB, gt=0.0)
    excitation: Excitation = DEFAULT_EXCITATION
