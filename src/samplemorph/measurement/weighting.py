from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def loudness_weight(level: NDArray[np.float64], *, floor: float) -> NDArray[np.float64]:
    """A weight over a reference's level field that counts each cell by how far it sits above the floor.

    The weights sum to one, so a reading weighted by them is a mean over what the reference sounds
    at and a cell holding nothing carries no charge. A reference at the floor everywhere reads every
    cell alike, which keeps a silent reference measurable.
    """
    above_floor = np.maximum(level - floor, 0.0)
    total = float(above_floor.sum())
    return above_floor / total if total > 0.0 else np.full_like(above_floor, 1.0 / above_floor.size)
