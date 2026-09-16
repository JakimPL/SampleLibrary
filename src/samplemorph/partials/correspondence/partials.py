from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from samplemorph.partials.voices import PartialVoices


def ordered_pairs(first: PartialVoices, second: PartialVoices) -> NDArray[np.intp]:
    """Which partial meets which, in frequency order and one to one, as index pairs.

    Every partial of the smaller set meets one of the larger, the pairs crossing nowhere, and the
    pairing chosen is the one whose partials travel the shortest weighted distance in pitch: a
    partial's move counts for as much of the sound as it carries. Shape: the result is ``(pairs, 2)``.
    """
    if first.count == 0 or second.count == 0:
        return np.zeros((0, 2), dtype=np.intp)

    rows, columns = (first, second) if first.count <= second.count else (second, first)
    row_order, column_order = np.argsort(rows.cents), np.argsort(columns.cents)
    cost = (rows.share[row_order, None] + columns.share[column_order]) * np.abs(
        rows.cents[row_order, None] - columns.cents[column_order]
    )
    pairs = _shortest_monotone_pairs(cost)
    matched = np.stack((row_order[pairs[:, 0]], column_order[pairs[:, 1]]), axis=1)
    return matched if first.count <= second.count else matched[:, ::-1]


def _shortest_monotone_pairs(cost: NDArray[np.float64]) -> NDArray[np.intp]:
    """Every row matched to a column of its own, the matches rising through the columns, at the least cost.

    Shapes: `cost` is ``(rows, columns)`` with rows no more than columns, and the result ``(rows, 2)``.
    """
    row_count, column_count = cost.shape
    reached = np.full((row_count + 1, column_count + 1), np.inf)
    reached[0] = 0.0
    for row in range(1, row_count + 1):
        reached[row, 1:] = np.minimum.accumulate(reached[row - 1, :-1] + cost[row - 1])
    pairs = np.empty((row_count, 2), dtype=np.intp)
    column = column_count
    for row in range(row_count, 0, -1):
        while column > row and reached[row, column] == reached[row, column - 1]:
            column -= 1
        pairs[row - 1] = (row - 1, column - 1)
        column -= 1
    return pairs


def nearest_pairs(
    first: PartialVoices, second: PartialVoices, *, cap_cents: float, taken: tuple[NDArray[np.intp], NDArray[np.intp]]
) -> NDArray[np.intp]:
    """Which partial meets which by pitch alone: each pair the nearest to the other, within `cap_cents`.

    A partial the two sounds hold in common holds still through the morph, and one the other sound
    has nothing near fades where it stands. Partials already met through their notes stay as they
    are. Shape: the result is ``(pairs, 2)``.
    """
    free = (_left_over(first.count, taken=taken[0]), _left_over(second.count, taken=taken[1]))
    if free[0].size == 0 or free[1].size == 0:
        return np.zeros((0, 2), dtype=np.intp)

    apart = np.abs(first.cents[free[0]][:, None] - second.cents[free[1]])
    nearest_second = apart.argmin(axis=1)
    nearest_first = apart.argmin(axis=0)
    rows = np.arange(free[0].shape[0])
    mutual = (nearest_first[nearest_second] == rows) & (apart[rows, nearest_second] <= cap_cents)
    return np.stack((free[0][rows[mutual]], free[1][nearest_second[mutual]]), axis=1).astype(np.intp)


def _left_over(count: int, *, taken: NDArray[np.intp]) -> NDArray[np.intp]:
    met = np.zeros(count, dtype=bool)
    met[taken] = True
    return np.flatnonzero(~met).astype(np.intp)
