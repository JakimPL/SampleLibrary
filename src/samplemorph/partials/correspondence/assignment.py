from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import linear_sum_assignment


def assign_with_fades(
    cost: NDArray[np.float64], *, first_fades: NDArray[np.float64], second_fades: NDArray[np.float64]
) -> NDArray[np.intp]:
    """Which of two sets meets which, every item free to fade on its own instead, at the least cost over all of them.

    Each item may meet one item of the other set at the cost that pair carries, or fade at its own
    cost, and the pairing returned is the one whose total cost is least: two notes meet where meeting
    costs both of them less than fading does. Shapes: `cost` is ``(first, second)``, the fades are
    ``(first,)`` and ``(second,)``, and the result ``(pairs, 2)``.
    """
    first_count, second_count = cost.shape
    if first_count == 0 or second_count == 0:
        return np.zeros((0, 2), dtype=np.intp)

    whole = np.full((first_count + second_count, first_count + second_count), np.inf)
    whole[:first_count, :second_count] = cost
    whole[:first_count, second_count:] = np.where(np.eye(first_count, dtype=bool), first_fades, np.inf)
    whole[first_count:, :second_count] = np.where(np.eye(second_count, dtype=bool).T, second_fades[:, None], np.inf)
    whole[first_count:, second_count:] = 0.0
    rows, columns = linear_sum_assignment(whole)
    met = (rows < first_count) & (columns < second_count)
    return np.stack((rows[met], columns[met]), axis=1).astype(np.intp)
