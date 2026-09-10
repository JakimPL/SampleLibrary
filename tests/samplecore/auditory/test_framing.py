from __future__ import annotations

import numpy as np
import pytest

from samplecore.auditory.framing import convolution_fft_size, frame_series, unit_sum_hann


def test_a_unit_sum_hann_sums_to_one_and_is_symmetric() -> None:
    kernel = unit_sum_hann(65)

    assert np.isclose(kernel.sum(), 1.0)
    assert np.allclose(kernel, kernel[::-1])


def test_frames_start_at_the_first_point_and_lie_inside_the_series() -> None:
    series = np.arange(20.0)

    frames = frame_series(series, window_length=8, hop_length=4)

    assert frames.shape == (4, 8)
    assert np.array_equal(frames[0], series[:8])
    assert np.array_equal(frames[-1], series[12:20])


def test_framing_keeps_every_leading_axis_in_place() -> None:
    series = np.arange(60.0).reshape(3, 20)

    frames = frame_series(series, window_length=8, hop_length=4)

    assert frames.shape == (3, 4, 8)
    assert np.array_equal(frames[2, 1], series[2, 4:12])


@pytest.mark.parametrize(
    ("signal_length", "kernel_length", "expected"),
    [(1, 1, 1), (5, 4, 8), (9, 8, 16), (1000, 25, 1024), (32768, 3528, 65536)],
)
def test_the_convolution_transform_is_the_smallest_power_of_two_holding_the_linear_length(
    signal_length: int, kernel_length: int, expected: int
) -> None:
    assert convolution_fft_size(signal_length, kernel_length) == expected
