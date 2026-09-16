from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from samplemorph.partials.tracks import CENTS_PER_OCTAVE, PartialTracks


@dataclass(frozen=True)
class PartialVoices:
    """Where each partial of a sound sits and how much of the sound it carries.

    `cents` is the amplitude-weighted pitch a partial holds over its life, and `share` its energy
    over the sound's. Shapes: both arrays are ``(partials,)``.
    """

    cents: NDArray[np.float64]
    share: NDArray[np.float64]

    @property
    def count(self) -> int:
        return int(self.cents.shape[0])


def partial_voices(tracks: PartialTracks) -> PartialVoices:
    """Each partial as one pitch and one share of the sound, which is what a pairing reads it by."""
    energy = tracks.amplitude.astype(np.float64) ** 2
    weight = energy.sum(axis=1)
    total = float(weight.sum())
    cents = CENTS_PER_OCTAVE * np.log2(tracks.frequency_hz.astype(np.float64))
    return PartialVoices(
        cents=np.where(weight > 0.0, (energy * cents).sum(axis=1) / np.where(weight > 0.0, weight, 1.0), cents[:, 0]),
        share=weight / total if total > 0.0 else np.zeros_like(weight),
    )


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
