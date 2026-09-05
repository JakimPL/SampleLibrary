from __future__ import annotations

import numpy as np

from samplecloud.backends.librosa_backend import LibrosaFeatureExtractor
from samplecore.storage.audio_store import NOMINAL_WAV_RATE


def _sine_wave(frame_count: int, *, channels: int = 1, frequency: float = 440.0) -> np.ndarray:
    times = np.arange(frame_count) / NOMINAL_WAV_RATE
    mono = np.sin(2.0 * np.pi * frequency * times)
    return np.tile(mono[:, None], (1, channels))


def test_extract_returns_a_finite_fixed_length_vector() -> None:
    extractor = LibrosaFeatureExtractor()

    vector = extractor.extract(_sine_wave(NOMINAL_WAV_RATE))

    assert vector.ndim == 1
    assert np.all(np.isfinite(vector))


def test_extract_returns_the_same_length_regardless_of_input_length() -> None:
    extractor = LibrosaFeatureExtractor()

    short_vector = extractor.extract(_sine_wave(32))
    long_vector = extractor.extract(_sine_wave(5 * NOMINAL_WAV_RATE))

    assert short_vector.shape == long_vector.shape


def test_extract_handles_a_very_short_waveform_without_raising() -> None:
    extractor = LibrosaFeatureExtractor()

    vector = extractor.extract(_sine_wave(4))

    assert np.all(np.isfinite(vector))


def test_extract_handles_stereo_input() -> None:
    extractor = LibrosaFeatureExtractor()

    vector = extractor.extract(_sine_wave(NOMINAL_WAV_RATE, channels=2))

    assert np.all(np.isfinite(vector))
