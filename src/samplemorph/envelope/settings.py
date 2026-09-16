from __future__ import annotations

from typing import Final

from pydantic import BaseModel, Field

from samplecore.models.base import FROZEN

DEFAULT_COEFFICIENT_COUNT: Final[int] = 40
DEFAULT_FLOOR_DB: Final[float] = 80.0
DEFAULT_SWITCH_WEIGHT: Final[float] = 1.0


class EnvelopeSettings(BaseModel):
    """Every constant an envelope morph reads, so a rendered file can name the settings it took.

    A spectrum's envelope is the shape its loudness over frequency takes when only its first
    `coefficient_count` cosines are kept, read down to `floor_db` under the loudest bin of the
    sound. `switch_weight` is the weight from which the second sound's excitation sounds under the
    moving envelope: at 1 the first sound's excitation sounds along the whole path, at 0 the
    second's, and a weight between the two hands the excitation over at that point of the path.
    """

    model_config = FROZEN

    coefficient_count: int = Field(default=DEFAULT_COEFFICIENT_COUNT, ge=1)
    floor_db: float = Field(default=DEFAULT_FLOOR_DB, gt=0.0)
    switch_weight: float = Field(default=DEFAULT_SWITCH_WEIGHT, ge=0.0, le=1.0)
