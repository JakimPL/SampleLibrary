from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

NEGLIGIBLE_MASS: Final[float] = 1e-9


@dataclass(frozen=True)
class TransportPlan:
    """How much of each first group travels to each second group, as pieces in frequency order.

    Masses are shares of one: the first groups of the pieces carry the first spectrum's shares, the
    second groups the second's, and both group indices only ever rise from one piece to the next.
    """

    first_groups: NDArray[np.intp]
    second_groups: NDArray[np.intp]
    masses: NDArray[np.float64]


def monotone_plan(first_masses: NDArray[np.float64], second_masses: NDArray[np.float64]) -> TransportPlan:
    """The optimal plan between two masses on a line, for any convex cost of the distance traveled.

    On a line the optimal plan pairs mass in order: the share of the first spectrum below any point
    meets the same share of the second. Merging both cumulative sums gives every breakpoint, and each
    stretch between two breakpoints is one piece, at most as many as both groups together.

    Raises:
        ValueError: either set of masses carries nothing, leaving no shares to pair.
    """
    first_total = float(first_masses.sum())
    second_total = float(second_masses.sum())
    if first_total <= 0.0 or second_total <= 0.0:
        raise ValueError("a transport plan pairs two masses that each carry something")

    first_cumulative = np.cumsum(first_masses) / first_total
    second_cumulative = np.cumsum(second_masses) / second_total
    breakpoints = np.union1d(first_cumulative, second_cumulative)
    breakpoints[-1] = 1.0
    lower = np.concatenate(([0.0], breakpoints[:-1]))
    masses = breakpoints - lower
    kept = masses > NEGLIGIBLE_MASS
    middles = 0.5 * (breakpoints + lower)[kept]
    return TransportPlan(
        first_groups=_group_at(first_cumulative, middles),
        second_groups=_group_at(second_cumulative, middles),
        masses=masses[kept],
    )


def _group_at(cumulative: NDArray[np.float64], shares: NDArray[np.float64]) -> NDArray[np.intp]:
    groups: NDArray[np.intp] = np.minimum(
        np.searchsorted(cumulative, shares, side="right"), cumulative.shape[0] - 1
    ).astype(np.intp)
    return groups
