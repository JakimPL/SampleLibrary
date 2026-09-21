from __future__ import annotations

from enum import StrEnum, unique
from typing import Final

import numpy as np

from samplemorph.geometry import (
    DEFAULT_ANALYSIS_WINDOW,
    DEFAULT_BINS_PER_OCTAVE,
    REFERENCE_FREQUENCY_HZ,
    SEMITONES_PER_OCTAVE,
    AnalysisWindow,
    LogFrequencyGeometry,
    log_frequency_geometry,
)

DEFAULT_TIME_COLUMNS: Final[int] = 64
DEFAULT_MAXIMUM_SHIFT_SEMITONES: Final[float] = 48.0


@unique
class Anchor(StrEnum):
    """Which band of a sound alignment moves to the reference band, if any.

    `NONE` keeps the picture where the analysis read it: every band holds the frequency it measured,
    a kick and a pad alike, and the grid is exactly as tall as the analysis range. `LOUDEST` moves
    the band carrying the most energy over the whole sound, which every kind of material has.
    `FUNDAMENTAL` moves the band a harmonic series is built on, so two sounds playing one note align
    on that note whichever of their partials is the strongest.
    """

    NONE = "none"
    LOUDEST = "loudest"
    FUNDAMENTAL = "fundamental"


DEFAULT_ANCHOR: Final[Anchor] = Anchor.NONE


def shift_headroom_bands(*, anchor: Anchor, maximum_shift_semitones: float, bands_per_semitone: float) -> int:
    """How many empty bands a grid carries at each end, so an anchoring rule moves content without losing it.

    Alignment translates the whole picture along the frequency axis, and a grid exactly as tall as
    the analysis range would push whatever passes its edge out of the picture. Reserving the largest
    shift at both ends keeps every band that entered the grid inside it, whatever pitch a sample sat
    at -- which matters most for bass material, whose distance from the reference band is greatest.
    A picture nothing moves needs no room to move in, so it stays as tall as the analysis.
    """
    if anchor is Anchor.NONE:
        return 0
    return int(round(maximum_shift_semitones * bands_per_semitone))


class GridGeometry(LogFrequencyGeometry):
    """The log-frequency analysis a sound image is read on, with the grid laid over it.

    The grid is `time_columns` wide and as tall as the analysis range plus the shift headroom the
    `anchor` rule asks for, and `maximum_shift_semitones` bounds how far alignment moves content.
    """

    anchor: Anchor = DEFAULT_ANCHOR
    time_columns: int
    maximum_shift_semitones: float

    @property
    def bands_per_semitone(self) -> float:
        return self.bins_per_octave / SEMITONES_PER_OCTAVE

    @property
    def shift_headroom_bands(self) -> int:
        return shift_headroom_bands(
            anchor=self.anchor,
            maximum_shift_semitones=self.maximum_shift_semitones,
            bands_per_semitone=self.bands_per_semitone,
        )

    @property
    def grid_shape(self) -> tuple[int, int]:
        return self.band_count + 2 * self.shift_headroom_bands, self.time_columns

    @property
    def reference_band(self) -> int:
        """The band an aligned image's anchor is moved to, at `REFERENCE_FREQUENCY_HZ`."""
        return int(round(self.bins_per_octave * np.log2(REFERENCE_FREQUENCY_HZ / self.minimum_frequency_hz)))


def grid_geometry(
    *,
    bins_per_octave: int = DEFAULT_BINS_PER_OCTAVE,
    anchor: Anchor = DEFAULT_ANCHOR,
    analysis_window: AnalysisWindow = DEFAULT_ANALYSIS_WINDOW,
) -> GridGeometry:
    analysis = log_frequency_geometry(bins_per_octave=bins_per_octave, analysis_window=analysis_window)
    return GridGeometry(
        **analysis.model_dump(),
        anchor=anchor,
        time_columns=DEFAULT_TIME_COLUMNS,
        maximum_shift_semitones=DEFAULT_MAXIMUM_SHIFT_SEMITONES,
    )
