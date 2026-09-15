from __future__ import annotations

from typing import Final

from pydantic import BaseModel, Field

from samplecore.models.base import FROZEN

DEFAULT_ANALYSIS_SECONDS: Final[float] = 0.093
DEFAULT_PEAK_DEPTH_DB: Final[float] = 60.0
DEFAULT_SOUND_DEPTH_DB: Final[float] = 80.0
DEFAULT_LOWEST_CURVATURE_RATIO: Final[float] = 0.1
DEFAULT_HIGHEST_CURVATURE_RATIO: Final[float] = 1.33
DEFAULT_LOCAL_PROMINENCE_DB: Final[float] = 12.0
DEFAULT_LOCAL_REACH_BINS: Final[int] = 16
DEFAULT_CONTINUATION_CENTS_PER_SECOND: Final[float] = 12000.0
DEFAULT_CONTINUATION_FLOOR_HZ: Final[float] = 3.0
DEFAULT_GAP_FRAMES: Final[int] = 2
DEFAULT_MINIMUM_TRACK_SECONDS: Final[float] = 0.04


class PartialSettings(BaseModel):
    """Every constant a partial analysis reads, so a rendered file can name the settings it took.

    Analysis: one Gaussian window about `analysis_seconds` long as heard, rounded to a power of two.
    Peaks: a peak stands within `peak_depth_db` of its frame's loudest peak and within
    `sound_depth_db` of the sound's loudest; it reads as a sinusoid when it rises `local_prominence_db`
    over the median of the `local_reach_bins` on either side, and its lobe's curvature over a
    stationary sinusoid's lies between `lowest_curvature_ratio` and `highest_curvature_ratio`. Tracks: a
    track continues to a peak within `continuation_cents_per_second` of heard time, or within
    `continuation_floor_hz`, whichever is wider, bridges up to `gap_frames` missing frames, and lasts
    at least `minimum_track_seconds`.
    """

    model_config = FROZEN

    analysis_seconds: float = Field(default=DEFAULT_ANALYSIS_SECONDS, gt=0.0)
    peak_depth_db: float = Field(default=DEFAULT_PEAK_DEPTH_DB, gt=0.0)
    sound_depth_db: float = Field(default=DEFAULT_SOUND_DEPTH_DB, gt=0.0)
    lowest_curvature_ratio: float = Field(default=DEFAULT_LOWEST_CURVATURE_RATIO, gt=0.0)
    highest_curvature_ratio: float = Field(default=DEFAULT_HIGHEST_CURVATURE_RATIO, gt=0.0)
    local_prominence_db: float = Field(default=DEFAULT_LOCAL_PROMINENCE_DB, gt=0.0)
    local_reach_bins: int = Field(default=DEFAULT_LOCAL_REACH_BINS, ge=1)
    continuation_cents_per_second: float = Field(default=DEFAULT_CONTINUATION_CENTS_PER_SECOND, gt=0.0)
    continuation_floor_hz: float = Field(default=DEFAULT_CONTINUATION_FLOOR_HZ, ge=0.0)
    gap_frames: int = Field(default=DEFAULT_GAP_FRAMES, ge=0)
    minimum_track_seconds: float = Field(default=DEFAULT_MINIMUM_TRACK_SECONDS, ge=0.0)
