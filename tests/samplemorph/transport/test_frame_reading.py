from __future__ import annotations

import numpy as np

from samplemorph.transport.frame_reading import read_frames

MAXIMUM_HALF_WIDTH = 8.0


def _ramp(frame_count: int) -> np.ndarray:
    return np.arange(frame_count, dtype=np.float32)[None, :]


def test_whole_positions_at_their_own_rate_return_the_frames_exactly() -> None:
    frames = np.random.default_rng(1).random((3, 10)).astype(np.float32)
    positions = np.arange(10, dtype=np.float64)

    read = read_frames(frames, positions=positions, rates=np.ones(10), maximum_half_width=MAXIMUM_HALF_WIDTH)

    assert np.array_equal(read, frames)


def test_a_position_between_two_frames_reads_the_line_between_them() -> None:
    read = read_frames(
        _ramp(10), positions=np.array([2.25, 6.5]), rates=np.ones(2), maximum_half_width=MAXIMUM_HALF_WIDTH
    )

    assert np.allclose(read, [[2.25, 6.5]])


def test_compressed_time_averages_every_frame_it_spans() -> None:
    frames = np.zeros((1, 20), dtype=np.float32)
    frames[0, 9] = 1.0

    stepped = read_frames(frames, positions=np.array([8.0]), rates=np.ones(1), maximum_half_width=MAXIMUM_HALF_WIDTH)
    averaged = read_frames(
        frames, positions=np.array([8.0]), rates=np.full(1, 4.0), maximum_half_width=MAXIMUM_HALF_WIDTH
    )

    assert stepped[0, 0] == 0.0
    assert averaged[0, 0] > 0.0


def test_positions_past_either_end_read_silence() -> None:
    frames = np.ones((1, 5), dtype=np.float32)

    read = read_frames(
        frames, positions=np.array([-3.0, 2.0, 9.0]), rates=np.ones(3), maximum_half_width=MAXIMUM_HALF_WIDTH
    )

    assert np.array_equal(read, [[0.0, 1.0, 0.0]])
