from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.measurement.perceptual_distance import (
    CDPAM_RATE_HZ,
    perceptual_distance,
    to_cdpam_block,
)

DURATION_SECONDS = 0.5
HEARD_RATE_HZ = 8363
LIGHT_NOISE = 0.01
HEAVY_NOISE = 0.20


def _tone(frequency_hz: float, *, rate_hz: int) -> NDArray[np.float64]:
    times = np.arange(int(rate_hz * DURATION_SECONDS)) / rate_hz
    return np.sin(2 * np.pi * frequency_hz * times)


def test_the_cdpam_block_resamples_to_cdpams_rate_and_leaves_the_unit_range() -> None:
    tone = _tone(440.0, rate_hz=NOMINAL_WAV_RATE)

    block = to_cdpam_block(tone, tone.shape[0], source_rate_hz=NOMINAL_WAV_RATE)

    assert block.ndim == 2
    assert block.shape[0] == 1
    expected_length = tone.shape[0] * CDPAM_RATE_HZ / NOMINAL_WAV_RATE
    assert abs(block.shape[1] - expected_length) <= 2
    assert np.abs(block).max() > 1.0


def test_the_cdpam_block_honors_a_heard_rate_lower_than_the_store_rate() -> None:
    tone = _tone(440.0, rate_hz=HEARD_RATE_HZ)

    block = to_cdpam_block(tone, tone.shape[0], source_rate_hz=HEARD_RATE_HZ)

    expected_length = tone.shape[0] * CDPAM_RATE_HZ / HEARD_RATE_HZ
    assert abs(block.shape[1] - expected_length) <= 2


def test_a_closer_reconstruction_reads_a_smaller_perceptual_distance() -> None:
    pytest.importorskip("cdpam")
    generator = np.random.default_rng(0)
    reference = _tone(440.0, rate_hz=NOMINAL_WAV_RATE)
    lightly_degraded = reference + LIGHT_NOISE * generator.standard_normal(reference.shape)
    heavily_degraded = reference + HEAVY_NOISE * generator.standard_normal(reference.shape)

    near = perceptual_distance(lightly_degraded, reference)
    far = perceptual_distance(heavily_degraded, reference)

    assert near < far
