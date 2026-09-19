from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from matplotlib.figure import Figure
from numpy.typing import NDArray

from samplemorph.measurement.ladders.axis import PooledAxis

PANEL_WIDTH_INCHES: Final[float] = 3.2
PANEL_HEIGHT_INCHES: Final[float] = 2.6
PICTURE_DPI: Final[int] = 110
COLOR_MAP: Final[str] = "magma"
UNREAD_SHADE: Final[str] = "#808080"
UNREAD_ALPHA: Final[float] = 0.45
COLOR_FLOOR_PERCENTILE: Final[float] = 5.0
OCTAVE_TICK_HZ: Final[tuple[float, ...]] = (125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0)


@dataclass(frozen=True)
class LadderPanel:
    """One path up a ladder as a picture: a label, and a grid per step.

    Shape: `grids` is ``(steps, bands, columns)``.
    """

    label: str
    grids: NDArray[np.float32]


@dataclass(frozen=True)
class LadderPicture:
    """Every path up one ladder, side by side, under a title, with the weight of each row and the bands the readings keep."""

    title: str
    panels: tuple[LadderPanel, ...]
    weights: tuple[float, ...]
    reading_bands: NDArray[np.bool_]


def draw_ladder(path: Path, picture: LadderPicture, *, axis: PooledAxis) -> None:
    """Draw every path of one ladder side by side, each step's spectrum averaged over time as one row.

    Rows run from the first end at the top to the second at the bottom, bands from low on the left
    to high on the right, in decibels under the grid's peak. A feature that moves draws a slanted
    ridge; a crossfade draws the two ends' ridges, one fading out as the other fades in. The bands
    the readings leave out are shaded, and the colors span what the read bands of every panel hold,
    from their quietest few percent to their loudest, so a ridge stands out however quiet the sound.
    """
    figure = Figure(figsize=(PANEL_WIDTH_INCHES * len(picture.panels), PANEL_HEIGHT_INCHES), layout="constrained")
    figure.suptitle(picture.title)
    frequencies = axis.band_frequencies
    ticks = [int(np.argmin(np.abs(frequencies - hertz))) for hertz in OCTAVE_TICK_HZ if hertz <= frequencies[-1]]
    unread = np.flatnonzero(~picture.reading_bands)
    every_profile = [axis.dynamic_range_db * (panel.grids.mean(axis=2) - 1.0) for panel in picture.panels]
    read = np.concatenate([profiles[:, picture.reading_bands].ravel() for profiles in every_profile])
    floor, ceiling = float(np.percentile(read, COLOR_FLOOR_PERCENTILE)), float(read.max())
    every_axes = np.atleast_1d(figure.subplots(1, len(picture.panels), sharey=True))
    for axes, panel, profiles in zip(every_axes, picture.panels, every_profile, strict=True):
        axes.imshow(profiles, aspect="auto", cmap=COLOR_MAP, vmin=floor, vmax=max(ceiling, floor + 1.0))
        for band in unread:
            axes.axvspan(band - 0.5, band + 0.5, color=UNREAD_SHADE, alpha=UNREAD_ALPHA, linewidth=0)
        axes.set_title(panel.label)
        axes.set_xticks(ticks, [_hertz_label(frequencies[tick]) for tick in ticks])
        axes.set_yticks(range(len(picture.weights)), [f"{weight:.3g}" for weight in picture.weights])
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=PICTURE_DPI)


def _hertz_label(hertz: float) -> str:
    return f"{hertz / 1000.0:.0f}k" if hertz >= 1000.0 else f"{hertz:.0f}"
