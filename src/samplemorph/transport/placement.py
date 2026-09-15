from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.transport.segmentation import LOWEST_MOVED_BIN, SHAPE_FLOOR, SpectralGroups

HALF_BIN: Final[float] = 0.5


def place_groups(
    shape: NDArray[np.float64],
    groups: SpectralGroups,
    *,
    piece_groups: NDArray[np.intp],
    piece_gains: NDArray[np.float64],
    piece_scales: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Deposit every piece's share of its group, each grain carried rigidly to its scaled position.

    A piece moves its group by a scale about zero frequency: a grain centered at bin ``k`` lands
    around ``k * scale``, keeping its own width, so a partial arrives as the lobe it was and a band
    or a comb spreads in position as a transposed one does. The grain's values between bins are read
    by a parabola through the logarithm of its three nearest bins, which is exact for the Gaussian
    lobe of a partial, and every deposit is scaled to the grain's own energy times the piece's gain.
    Whatever lands below `LOWEST_MOVED_BIN` or above the last bin leaves the spectrum. Shape: the
    result is ``(bins,)``, like `shape`.
    """
    bin_count = shape.shape[0]
    grain_counts = groups.group_grain_count[piece_groups]
    piece_of_combination = np.repeat(np.arange(piece_groups.shape[0]), grain_counts)
    grain_of_combination = np.repeat(groups.group_first_grain[piece_groups], grain_counts) + _offsets(grain_counts)
    starts = groups.grain_starts[grain_of_combination]
    ends = groups.grain_ends[grain_of_combination]
    shifts = groups.grain_center[grain_of_combination] * (piece_scales[piece_of_combination] - 1.0)
    widths = ends - starts

    combination_of_element = np.repeat(np.arange(widths.shape[0]), widths)
    first_targets = np.ceil(starts - HALF_BIN + shifts).astype(np.int64)
    targets = first_targets[combination_of_element] + _offsets(widths)
    values = _read_grain(
        np.log(np.maximum(shape, SHAPE_FLOOR)),
        positions=targets - shifts[combination_of_element],
        starts=starts[combination_of_element],
        ends=ends[combination_of_element],
    )
    totals = np.bincount(combination_of_element, weights=values, minlength=widths.shape[0])
    scales = np.where(
        totals > 0.0,
        piece_gains[piece_of_combination] * groups.grain_energy[grain_of_combination] / np.maximum(totals, SHAPE_FLOOR),
        0.0,
    )
    deposits = values * scales[combination_of_element]
    inside = (targets >= LOWEST_MOVED_BIN) & (targets < bin_count)
    placed: NDArray[np.float64] = np.bincount(targets[inside], weights=deposits[inside], minlength=bin_count)
    return placed


def _offsets(counts: NDArray[np.intp]) -> NDArray[np.intp]:
    """Each element's position within its run, for runs of `counts` laid end to end."""
    run_starts = np.repeat(np.cumsum(counts) - counts, counts)
    offsets: NDArray[np.intp] = np.arange(run_starts.shape[0]) - run_starts
    return offsets


def _read_grain(
    log_shape: NDArray[np.float64],
    *,
    positions: NDArray[np.float64],
    starts: NDArray[np.intp],
    ends: NDArray[np.intp],
) -> NDArray[np.float64]:
    nearest = np.clip(np.rint(positions).astype(np.int64), starts, ends - 1)
    below = log_shape[np.maximum(nearest - 1, starts)]
    center = log_shape[nearest]
    above = log_shape[np.minimum(nearest + 1, ends - 1)]
    offset = positions - nearest
    values: NDArray[np.float64] = np.exp(
        center + offset * (above - below) / 2.0 + offset**2 * (above - 2.0 * center + below) / 2.0
    )
    return values
