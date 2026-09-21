from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def read_frames(
    frames: NDArray[np.float32],
    *,
    positions: NDArray[np.float64],
    rates: NDArray[np.float64],
    maximum_half_width: float,
) -> NDArray[np.float32]:
    """Read rows of frames at fractional frame positions, each through a triangle as wide as the local rate.

    Where time is compressed, one output frame stands for several source frames and averages all of
    them; where it is stretched or kept, the triangle spans one frame each way and interpolates the
    two neighbors, which returns a frame exactly at a whole position. The weights are normalized over
    the whole triangle, so a position reaching past either end reads the missing frames as silence.
    Shapes: `frames` is ``(rows, source frames)``, and the result ``(rows, positions)``.
    """
    half_widths = np.clip(rates, 1.0, maximum_half_width)
    reach = int(np.ceil(maximum_half_width))
    nearest_below = np.floor(positions).astype(np.int64)
    source_count = frames.shape[1]
    read = np.zeros((frames.shape[0], positions.shape[0]), dtype=np.float32)
    kernel_sums = np.zeros(positions.shape[0], dtype=np.float32)
    for offset in range(-reach, reach + 2):
        indices = nearest_below + offset
        weights = np.maximum(1.0 - np.abs(indices - positions) / half_widths, 0.0).astype(np.float32)
        kernel_sums += weights
        within = (indices >= 0) & (indices < source_count) & (weights > 0.0)
        read[:, within] += frames[:, indices[within]] * weights[within]
    normalized: NDArray[np.float32] = read / kernel_sums
    return normalized
