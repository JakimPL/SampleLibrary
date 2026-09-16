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
DEFAULT_MINIMUM_TRACK_SECONDS: Final[float] = 0.1
DEFAULT_RESIDUAL_MARGIN_DB: Final[float] = 3.0
DEFAULT_FLOOR_REACH_BINS: Final[int] = 8
DEFAULT_FLOOR_SMOOTHING_BINS: Final[int] = 5
DEFAULT_HARMONIC_COUNT: Final[int] = 20
DEFAULT_LOWEST_NOTE_HZ: Final[float] = 32.7
DEFAULT_HARMONIC_CENTS: Final[float] = 50.0
DEFAULT_NOTE_SHARE_FLOOR: Final[float] = 0.02
DEFAULT_LARGEST_NOTE_COUNT: Final[int] = 8
DEFAULT_LARGEST_INHARMONICITY: Final[float] = 1e-3
DEFAULT_SMALLEST_NOTE_HARMONICS: Final[int] = 3
DEFAULT_NOTE_DENSITY: Final[float] = 0.7


class NoteSettings(BaseModel):
    """Every constant the notes of a sound are read by, so a rendered file can name the settings it took.

    A note is sought over its first `harmonic_count` harmonics, down to `lowest_note_hz`, and a
    partial belongs to a harmonic when it stands within `harmonic_cents` of it, stretched by the
    inharmonicity fitted for that note, up to `largest_inharmonicity`. A note sounds through at least
    `smallest_note_harmonics` of its harmonics and through `note_density` of those between the lowest
    and the highest it holds, and a sound holds at most `largest_note_count` notes, each carrying at
    least `note_share_floor` of what its partials carry.
    """

    model_config = FROZEN

    harmonic_count: int = Field(default=DEFAULT_HARMONIC_COUNT, ge=1)
    lowest_note_hz: float = Field(default=DEFAULT_LOWEST_NOTE_HZ, gt=0.0)
    harmonic_cents: float = Field(default=DEFAULT_HARMONIC_CENTS, gt=0.0)
    note_share_floor: float = Field(default=DEFAULT_NOTE_SHARE_FLOOR, gt=0.0, le=1.0)
    largest_note_count: int = Field(default=DEFAULT_LARGEST_NOTE_COUNT, ge=1)
    largest_inharmonicity: float = Field(default=DEFAULT_LARGEST_INHARMONICITY, ge=0.0)
    smallest_note_harmonics: int = Field(default=DEFAULT_SMALLEST_NOTE_HARMONICS, ge=1)
    note_density: float = Field(default=DEFAULT_NOTE_DENSITY, gt=0.0, le=1.0)


class PartialSettings(BaseModel):
    """Every constant a partial analysis reads, so a rendered file can name the settings it took.

    Analysis: one Gaussian window about `analysis_seconds` long as heard, rounded to a power of two.
    Peaks: a peak stands within `peak_depth_db` of its frame's loudest peak and within
    `sound_depth_db` of the sound's loudest; it reads as a sinusoid when it rises `local_prominence_db`
    over the median of the `local_reach_bins` on either side, and its lobe's curvature over a
    stationary sinusoid's lies between `lowest_curvature_ratio` and `highest_curvature_ratio`. Tracks: a
    track continues to a peak within `continuation_cents_per_second` of heard time, or within
    `continuation_floor_hz`, whichever is wider, bridges up to `gap_frames` missing frames, and lasts
    at least `minimum_track_seconds`, which a noise peak holds for about one window and a partial for
    far longer. Residual: what a partial's lobe explains leaves the spectrum with `residual_margin_db`
    of headroom, down to a floor read as the least energy within `floor_reach_bins`, smoothed over
    `floor_smoothing_bins`. Notes: `notes` names how the partials are read as notes.
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
    residual_margin_db: float = Field(default=DEFAULT_RESIDUAL_MARGIN_DB, ge=0.0)
    floor_reach_bins: int = Field(default=DEFAULT_FLOOR_REACH_BINS, ge=1)
    floor_smoothing_bins: int = Field(default=DEFAULT_FLOOR_SMOOTHING_BINS, ge=1)
    notes: NoteSettings = NoteSettings()
