from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

LOUDNESS_UNITS_PER_SONE_DOUBLING: Final[float] = 10.0


@dataclass(frozen=True)
class LoudnessPath:
    """How loud each point of a path is, in LUFS, beside the weight it stands at, ends first and last.

    A path is held against two lines between its ends: the straight line in loudness units, and
    the straight line in sones, where ten loudness units double how loud a sound is heard. A point
    falling under the first is heard dipping between two sounds. A silent point reads negative
    infinity, and every offset reading it is not a number.
    """

    weights: tuple[float, ...]
    loudness_lufs: tuple[float, ...]

    def line_offset_lu(self, index: int) -> float:
        """How far one point sits above the straight line between the ends' loudness."""
        weight = self.weights[index]
        line = (1.0 - weight) * self.loudness_lufs[0] + weight * self.loudness_lufs[-1]
        return _finite_difference(self.loudness_lufs[index], line)

    def sone_offset_lu(self, index: int) -> float:
        """How far one point sits above the straight line between the ends' loudness in sones, in loudness units."""
        weight = self.weights[index]
        sones = (1.0 - weight) * 2.0 ** (self.loudness_lufs[0] / LOUDNESS_UNITS_PER_SONE_DOUBLING) + weight * 2.0 ** (
            self.loudness_lufs[-1] / LOUDNESS_UNITS_PER_SONE_DOUBLING
        )
        line = LOUDNESS_UNITS_PER_SONE_DOUBLING * float(np.log2(sones)) if sones > 0.0 else -np.inf
        return _finite_difference(self.loudness_lufs[index], line)

    @property
    def largest_dip_lu(self) -> float:
        """How far the quietest point between the ends falls under the loudness line, zero when none falls under it."""
        offsets = [self.line_offset_lu(index) for index in range(1, len(self.weights) - 1)]
        finite = [offset for offset in offsets if np.isfinite(offset)]
        return max(0.0, -min(finite)) if finite else 0.0


def _finite_difference(value: float, line: float) -> float:
    return value - line if np.isfinite(value) and np.isfinite(line) else float("nan")
