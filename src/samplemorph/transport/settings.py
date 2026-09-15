from __future__ import annotations

from typing import Final

from pydantic import BaseModel, Field

from samplecore.models.base import FROZEN

DEFAULT_ONSET_GUARD_FRAMES: Final[int] = 8
DEFAULT_DENSITY_EXPONENT: Final[float] = 1.0 / 3.0
DEFAULT_DENSITY_GATE_DB: Final[float] = 60.0
DEFAULT_UNIFORM_SHARE: Final[float] = 0.25
DEFAULT_MAXIMUM_READING_HALF_WIDTH: Final[float] = 8.0
DEFAULT_OUTLINE_FRAME_REACH: Final[int] = 2
DEFAULT_OUTLINE_BIN_REACH: Final[int] = 2
DEFAULT_PEAK_PROMINENCE_DB: Final[float] = 12.0
DEFAULT_LEVEL_EXPONENT: Final[float] = 1.0 / 3.0
DEFAULT_SILENT_SHAPE_DEPTH_DB: Final[float] = 80.0


class TransportSettings(BaseModel):
    """Every constant a transport reads, so a rendered file can name the settings it took.

    Time: `onset_guard_frames` is how far around the onset both sources are read at their own rate;
    after it, each sound's frames carry a mass of their energy raised to `density_exponent`, gated
    `density_gate_db` under the loudest frame and mixed with a uniform `uniform_share`; a compressed
    stretch of time is read through a triangle up to `maximum_reading_half_width` frames wide.
    Frequency: the outline that cuts a spectrum into groups is smoothed `outline_frame_reach` frames
    and `outline_bin_reach` bins each way, and a group stands for every peak at least
    `peak_prominence_db` prominent. Level: frame energies meet on a power mean at `level_exponent`,
    and a frame is read against its sound's mean spectrum `silent_shape_depth_db` under the loudest
    frame, which gives a silent frame a shape to move.
    """

    model_config = FROZEN

    onset_guard_frames: int = Field(default=DEFAULT_ONSET_GUARD_FRAMES, ge=0)
    density_exponent: float = Field(default=DEFAULT_DENSITY_EXPONENT, gt=0.0)
    density_gate_db: float = Field(default=DEFAULT_DENSITY_GATE_DB, gt=0.0)
    uniform_share: float = Field(default=DEFAULT_UNIFORM_SHARE, gt=0.0, le=1.0)
    maximum_reading_half_width: float = Field(default=DEFAULT_MAXIMUM_READING_HALF_WIDTH, ge=1.0)
    outline_frame_reach: int = Field(default=DEFAULT_OUTLINE_FRAME_REACH, ge=0)
    outline_bin_reach: int = Field(default=DEFAULT_OUTLINE_BIN_REACH, ge=0)
    peak_prominence_db: float = Field(default=DEFAULT_PEAK_PROMINENCE_DB, gt=0.0)
    level_exponent: float = Field(default=DEFAULT_LEVEL_EXPONENT, gt=0.0)
    silent_shape_depth_db: float = Field(default=DEFAULT_SILENT_SHAPE_DEPTH_DB, gt=0.0)
