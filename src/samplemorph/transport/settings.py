from __future__ import annotations

from typing import Final

from pydantic import BaseModel, Field

from samplecore.models.base import FROZEN

DEFAULT_ONSET_GUARD_FRAMES: Final[int] = 8
DEFAULT_DENSITY_EXPONENT: Final[float] = 1.0 / 3.0
DEFAULT_DENSITY_GATE_DB: Final[float] = 60.0
DEFAULT_UNIFORM_SHARE: Final[float] = 0.25
DEFAULT_MAXIMUM_READING_HALF_WIDTH: Final[float] = 8.0


class TransportSettings(BaseModel):
    """Every constant the time map reads, so a rendered file can name the settings it took.

    Time: `onset_guard_frames` is how far around the onset both sources are read at their own rate;
    after it, each sound's frames carry a mass of their energy raised to `density_exponent`, gated
    `density_gate_db` under the loudest frame and mixed with a uniform `uniform_share`; a compressed
    stretch of time is read through a triangle up to `maximum_reading_half_width` frames wide.
    """

    model_config = FROZEN

    onset_guard_frames: int = Field(default=DEFAULT_ONSET_GUARD_FRAMES, ge=0)
    density_exponent: float = Field(default=DEFAULT_DENSITY_EXPONENT, gt=0.0)
    density_gate_db: float = Field(default=DEFAULT_DENSITY_GATE_DB, gt=0.0)
    uniform_share: float = Field(default=DEFAULT_UNIFORM_SHARE, gt=0.0, le=1.0)
    maximum_reading_half_width: float = Field(default=DEFAULT_MAXIMUM_READING_HALF_WIDTH, ge=1.0)
