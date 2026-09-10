from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pytest

from samplecore.auditory.sound_type import SoundType, sound_type_reading

CONTAINER_RATE_HZ = 44100
LOW_HEARD_RATE_HZ = 8363
CLIP_SECONDS = 1.0
FUNDAMENTAL_HZ = 440.0
HARMONIC_WEIGHTS = (1.0, 0.5, 0.25)
DECAY_NEPERS = 8.0
CLICK_SECONDS = 0.001
PULSE_PERIOD_SECONDS = 0.01
NOISE_SEED = 5


def _times(sample_rate_hz: int) -> np.ndarray:
    return np.arange(int(CLIP_SECONDS * sample_rate_hz)) / sample_rate_hz


def _decay(sample_rate_hz: int) -> np.ndarray:
    return np.exp(-np.linspace(0.0, DECAY_NEPERS, int(CLIP_SECONDS * sample_rate_hz)))


def harmonic_tone(sample_rate_hz: int) -> np.ndarray:
    times = _times(sample_rate_hz)
    return sum(
        weight * np.sin(2.0 * np.pi * FUNDAMENTAL_HZ * index * times)
        for index, weight in enumerate(HARMONIC_WEIGHTS, 1)
    )


def decaying_tone(sample_rate_hz: int) -> np.ndarray:
    return harmonic_tone(sample_rate_hz) * _decay(sample_rate_hz)


def white_noise(sample_rate_hz: int) -> np.ndarray:
    return np.random.default_rng(NOISE_SEED).normal(size=int(CLIP_SECONDS * sample_rate_hz))


def noise_burst(sample_rate_hz: int) -> np.ndarray:
    return white_noise(sample_rate_hz) * _decay(sample_rate_hz)


def click(sample_rate_hz: int) -> np.ndarray:
    signal = np.zeros(int(CLIP_SECONDS * sample_rate_hz))
    length = int(CLICK_SECONDS * sample_rate_hz)
    signal[:length] = np.hanning(length)
    return signal


def pulse_train(sample_rate_hz: int) -> np.ndarray:
    signal = np.zeros(int(CLIP_SECONDS * sample_rate_hz))
    signal[:: int(PULSE_PERIOD_SECONDS * sample_rate_hz)] = 1.0
    return signal


@dataclass(frozen=True)
class SoundTypeCase:
    name: str
    build: Callable[[int], np.ndarray]
    sample_rate_hz: int
    expected: SoundType


SOUND_TYPE_CASES = (
    SoundTypeCase("sustained harmonic tone", harmonic_tone, CONTAINER_RATE_HZ, SoundType.TONAL),
    SoundTypeCase("harmonic tone at a low heard rate", harmonic_tone, LOW_HEARD_RATE_HZ, SoundType.TONAL),
    SoundTypeCase("pulse train, flat yet periodic", pulse_train, CONTAINER_RATE_HZ, SoundType.TONAL),
    SoundTypeCase("decaying noise burst", noise_burst, CONTAINER_RATE_HZ, SoundType.PERCUSSIVE),
    SoundTypeCase("single click", click, CONTAINER_RATE_HZ, SoundType.PERCUSSIVE),
    SoundTypeCase("decaying harmonic tone, kick-like", decaying_tone, CONTAINER_RATE_HZ, SoundType.PERCUSSIVE),
    SoundTypeCase("sustained white noise", white_noise, CONTAINER_RATE_HZ, SoundType.NOISE),
)


@pytest.mark.parametrize("case", SOUND_TYPE_CASES, ids=lambda case: case.name)
def test_the_reading_resolves_synthetic_material_to_its_kind(case: SoundTypeCase) -> None:
    reading = sound_type_reading(case.build(case.sample_rate_hz), sample_rate_hz=case.sample_rate_hz)

    assert reading.sound_type is case.expected
    assert 0.0 <= reading.flatness <= 1.0
    assert 0.0 <= reading.percussiveness <= 1.0
    assert 0.0 <= reading.harmonicity <= 1.0


def test_the_readings_order_the_way_the_material_does() -> None:
    tone = sound_type_reading(harmonic_tone(CONTAINER_RATE_HZ), sample_rate_hz=CONTAINER_RATE_HZ)
    noise = sound_type_reading(white_noise(CONTAINER_RATE_HZ), sample_rate_hz=CONTAINER_RATE_HZ)
    burst = sound_type_reading(noise_burst(CONTAINER_RATE_HZ), sample_rate_hz=CONTAINER_RATE_HZ)

    assert noise.flatness > tone.flatness
    assert burst.percussiveness > tone.percussiveness
    assert tone.harmonicity > noise.harmonicity


def test_silence_has_nothing_to_classify() -> None:
    with pytest.raises(ValueError, match="silent"):
        sound_type_reading(np.zeros(4096), sample_rate_hz=CONTAINER_RATE_HZ)
