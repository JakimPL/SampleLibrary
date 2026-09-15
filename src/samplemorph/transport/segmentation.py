from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy.signal import find_peaks

LOWEST_MOVED_BIN: Final[int] = 1
SHAPE_FLOOR: Final[float] = 1e-30
OUTLINE_FLOOR_RATIO: Final[float] = 1e-10


@dataclass(frozen=True)
class SpectralGroups:
    """A spectrum cut into groups, one per prominent peak of its outline, and each group into grains.

    A group is one mass for the transport plan; a grain, cut at the raw spectrum's own valleys, is
    the piece a placement carries rigidly, so a partial travels as one lobe. Groups and grains are
    in frequency order, the grains of one group contiguous, and every bin from `LOWEST_MOVED_BIN` up
    belongs to exactly one grain. Starts and ends are bins, centers fractional bins.
    """

    group_energy: NDArray[np.float64]
    group_center: NDArray[np.float64]
    grain_starts: NDArray[np.intp]
    grain_ends: NDArray[np.intp]
    grain_groups: NDArray[np.intp]
    grain_energy: NDArray[np.float64]
    grain_center: NDArray[np.float64]

    @property
    def group_count(self) -> int:
        return int(self.group_energy.shape[0])

    @property
    def group_first_grain(self) -> NDArray[np.intp]:
        first: NDArray[np.intp] = np.searchsorted(self.grain_groups, np.arange(self.group_count)).astype(np.intp)
        return first

    @property
    def group_grain_count(self) -> NDArray[np.intp]:
        counts: NDArray[np.intp] = np.bincount(self.grain_groups, minlength=self.group_count).astype(np.intp)
        return counts


def segment_spectrum(
    shape: NDArray[np.float64], outline: NDArray[np.float64], *, prominence_db: float
) -> SpectralGroups:
    """Cut one frame's spectrum into groups at its outline's valleys and into grains at its own.

    The outline decides the groups: a group is born for every outline peak standing `prominence_db`
    above its surroundings and ends at the lowest outline point before the next, so noise and a
    partial's skirts join the nearest prominent peak. The grains follow every valley of the raw
    shape, which keeps each lobe whole when it moves.
    """
    moved_shape = np.maximum(shape[LOWEST_MOVED_BIN:], SHAPE_FLOOR)
    group_starts = _group_starts(outline[LOWEST_MOVED_BIN:], prominence_db=prominence_db)
    grain_starts = np.union1d(group_starts, _valleys(moved_shape)).astype(np.intp)
    bins = np.arange(moved_shape.shape[0], dtype=np.float64) + LOWEST_MOVED_BIN
    grain_energy = np.add.reduceat(moved_shape, grain_starts)
    grain_center = np.add.reduceat(moved_shape * bins, grain_starts) / grain_energy
    grain_groups = (np.searchsorted(group_starts, grain_starts, side="right") - 1).astype(np.intp)
    group_energy = np.bincount(grain_groups, weights=grain_energy, minlength=group_starts.shape[0])
    group_center = np.bincount(grain_groups, weights=grain_energy * grain_center, minlength=group_starts.shape[0])
    return SpectralGroups(
        group_energy=group_energy,
        group_center=group_center / group_energy,
        grain_starts=grain_starts + LOWEST_MOVED_BIN,
        grain_ends=np.append(grain_starts[1:], moved_shape.shape[0]).astype(np.intp) + LOWEST_MOVED_BIN,
        grain_groups=grain_groups,
        grain_energy=grain_energy,
        grain_center=grain_center,
    )


def _group_starts(outline: NDArray[np.float64], *, prominence_db: float) -> NDArray[np.intp]:
    """The first bin of every group: the start, then the lowest outline point between each two prominent peaks."""
    decibels = 10.0 * np.log10(outline + OUTLINE_FLOOR_RATIO * max(float(outline.max()), SHAPE_FLOOR))
    edge = float(decibels.min()) - 2.0 * prominence_db
    peaks, _ = find_peaks(np.concatenate(([edge], decibels, [edge])), prominence=prominence_db)
    peaks = peaks - 1
    if peaks.shape[0] < 2:
        return np.zeros(1, dtype=np.intp)

    lengths = np.diff(peaks)
    segment_of = np.repeat(np.arange(lengths.shape[0]), lengths)
    positions = np.arange(peaks[0], peaks[-1])
    lowest = np.minimum.reduceat(decibels[peaks[0] : peaks[-1]], lengths.cumsum() - lengths)
    candidates = np.flatnonzero(decibels[positions] == lowest[segment_of])
    _, first_candidate = np.unique(segment_of[candidates], return_index=True)
    valleys = positions[candidates[first_candidate]]
    return np.union1d([0], valleys).astype(np.intp)


def _valleys(shape: NDArray[np.float64]) -> NDArray[np.intp]:
    falling_into = shape[1:-1] <= shape[:-2]
    rising_out = shape[1:-1] < shape[2:]
    valleys: NDArray[np.intp] = (np.flatnonzero(falling_into & rising_out) + 1).astype(np.intp)
    return valleys
