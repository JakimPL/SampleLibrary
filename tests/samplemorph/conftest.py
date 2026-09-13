from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray

from samplecore.storage.audio_store import NOMINAL_WAV_RATE

TEST_FRAME_COUNT = 8192
HARMONIC_WEIGHTS = (1.0, 0.5, 0.25, 0.125)


def harmonic_tone(
    frame_count: int, *, frequency: float, weights: tuple[float, ...] = HARMONIC_WEIGHTS
) -> NDArray[np.float64]:
    """A stationary harmonic template -- the same instrument at two frequencies, not two sounds."""
    times = np.arange(frame_count) / NOMINAL_WAV_RATE
    mono = np.zeros(frame_count)
    for index, weight in enumerate(weights, start=1):
        mono += weight * np.sin(2 * np.pi * frequency * index * times)
    return mono[:, None]


def noise_burst(frame_count: int, *, seed: int) -> NDArray[np.float64]:
    """A fast-decaying noise transient, percussive and with no fundamental to find."""
    envelope = np.exp(-np.linspace(0.0, 8.0, frame_count))
    noise = np.random.default_rng(seed).normal(size=frame_count)
    return (envelope * noise)[:, None]


@pytest.fixture
def tone() -> NDArray[np.float64]:
    return harmonic_tone(TEST_FRAME_COUNT, frequency=440.0)
