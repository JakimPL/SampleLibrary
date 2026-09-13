from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

SILENT_PEAK: Final[float] = 1e-6


def peak_level(magnitude: NDArray[np.floating]) -> float:
    """The level a magnitude is read relative to: its own peak, held above `SILENT_PEAK` for silence."""
    return max(float(magnitude.max()), SILENT_PEAK)


def floor_level(peak: float, *, dynamic_range_db: float) -> float:
    """The level `dynamic_range_db` below `peak`, under which a magnitude reads as silence."""
    return float(peak * 10.0 ** (-dynamic_range_db / 20.0))
