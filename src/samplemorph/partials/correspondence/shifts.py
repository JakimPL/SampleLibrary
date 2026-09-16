from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy.ndimage import gaussian_filter1d

from samplemorph.partials.places import PartialPlaces
from samplemorph.partials.profile import Correspondence

SHIFT_REACH_CENTS: Final[float] = 4800.0
SHIFT_STEP_CENTS: Final[float] = 5.0
SHIFT_FLOOR: Final[float] = 0.1
SMALLEST_AGREEING_LINE: Final[int] = 2


@dataclass(frozen=True)
class AgreedShifts:
    """The moves in pitch two sounds travel by: the ones they agree on as a whole, and the one each line makes.

    `cents` holds the intervals many heavy pairs travel alike and `weight` how much of the two sounds
    stands behind each. `by_channel` holds the move the line a channel belongs to makes, and reads as
    NaN for a channel whose line makes none, which leaves that channel free to travel by any of the
    moves the two sounds agree on. Shapes: `cents` and `weight` are ``(shifts,)``, `by_channel` is
    ``(first channels,)``.
    """

    cents: NDArray[np.float64]
    weight: NDArray[np.float64]
    by_channel: NDArray[np.float64]

    @property
    def count(self) -> int:
        return int(self.cents.shape[0])


def no_shifts(channel_count: int) -> AgreedShifts:
    """The moves of a pair of sounds read before any pairing stands, which leaves every channel free to travel."""
    return AgreedShifts(cents=np.zeros(0), weight=np.zeros(0), by_channel=np.full(channel_count, np.nan))


def agreed_shifts(
    first: PartialPlaces,
    second: PartialPlaces,
    *,
    matched: NDArray[np.intp],
    lines: NDArray[np.intp],
    correspondence: Correspondence,
) -> AgreedShifts:
    """The moves a pairing makes over and over: the heaviest of them, and the move each line travels by.

    Each pair of partials votes for the interval it travels, weighed by what the two carry, and the
    intervals many heavy pairs vote for alike stand out as peaks of that weight once it is spread
    over the correspondence's shift spread. A line that carries at least `SMALLEST_AGREEING_LINE`
    pairs travels by the move its own pairs stand on, which holds a harmonic series together where
    two of them cross at one frequency. Shapes: `matched` is ``(pairs, 2)`` and `lines` is
    ``(first channels,)``.
    """
    if matched.shape[0] == 0 or correspondence.largest_shift_count == 0:
        return no_shifts(first.count)

    moved = first.cents[matched[:, 0]] - second.cents[matched[:, 1]]
    weight = first.share[matched[:, 0]] + second.share[matched[:, 1]]
    edges = np.arange(-SHIFT_REACH_CENTS, SHIFT_REACH_CENTS + SHIFT_STEP_CENTS, SHIFT_STEP_CENTS)
    voted, _ = np.histogram(moved, bins=edges, weights=weight)
    density = gaussian_filter1d(voted, sigma=correspondence.shift_spread_cents / SHIFT_STEP_CENTS, mode="constant")
    peak_cents, peak_weight = _peaks(
        density, centers=0.5 * (edges[:-1] + edges[1:]), largest_count=correspondence.largest_shift_count
    )
    return AgreedShifts(
        cents=peak_cents,
        weight=peak_weight,
        by_channel=_line_shifts(moved, weight=weight, voting=lines[matched[:, 0]], lines=lines),
    )


def _peaks(
    density: NDArray[np.float64], *, centers: NDArray[np.float64], largest_count: int
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """The heaviest moves a density stands on, each one standing taller than the moves on either side of it."""
    tallest = float(density.max())
    if tallest <= 0.0:
        return np.zeros(0), np.zeros(0)

    padded = np.pad(density, 1)
    standing = np.flatnonzero((density >= padded[:-2]) & (density > padded[2:]) & (density >= SHIFT_FLOOR * tallest))
    found = np.sort(standing[np.argsort(density[standing])[::-1][:largest_count]])
    return centers[found], density[found]


def _line_shifts(
    moved: NDArray[np.float64], *, weight: NDArray[np.float64], voting: NDArray[np.intp], lines: NDArray[np.intp]
) -> NDArray[np.float64]:
    """The move each line travels by, read as the move its own pairs stand on, and NaN for a line making none."""
    held = np.full(lines.shape[0], np.nan)
    for line in np.unique(voting):
        votes = voting == line
        if int(votes.sum()) >= SMALLEST_AGREEING_LINE:
            held[lines == line] = _standing(moved[votes], weight=weight[votes])
    return held


def _standing(moved: NDArray[np.float64], *, weight: NDArray[np.float64]) -> float:
    """The move a line stands on, the one half of what its pairs carry travels at or under."""
    order = np.argsort(moved)
    running = np.cumsum(weight[order])
    return float(moved[order][np.searchsorted(running, 0.5 * float(running[-1]))])
