from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from numpy.typing import NDArray


def hann_taper(length: int) -> NDArray[np.float64]:
    """A symmetric Hann window of `length` points, the taper every windowed reading here shares."""
    taper: NDArray[np.float64] = np.hanning(length)
    return taper


def unit_sum_hann(length: int) -> NDArray[np.float64]:
    """A Hann window of `length` points scaled to sum to one, so it averages what it is laid over."""
    taper = hann_taper(length)
    return taper / taper.sum()


def frame_series(values: NDArray[np.float64], *, window_length: int, hop_length: int) -> NDArray[np.float64]:
    """Read a series along its last axis as frames `window_length` long, placed `hop_length` apart.

    Frames start at the series' first point and each lies fully inside it, so every frame reads
    real values. A frame axis is added before the window axis, giving ``(..., frames, window_length)``.

    Raises:
        ValueError: the series is shorter than one window.
    """
    windows = sliding_window_view(values, window_length, axis=-1)
    framed: NDArray[np.float64] = windows[..., ::hop_length, :]
    return framed


def convolution_fft_size(signal_length: int, kernel_length: int) -> int:
    """The transform size a linear convolution of these two lengths runs at.

    The smallest power of two holding the full linear length keeps a circular transform free of
    wrap-around, and every applier of one design reading the size from here lands on the same
    transform, so their results agree to rounding.
    """
    return 1 << (signal_length + kernel_length - 2).bit_length()
