from __future__ import annotations

import numpy as np

from samplecloud.backends.librosa_backend import (
    MFCC_COUNT,
    NO_ONSET_ATTACK_FRACTION,
    LibrosaFeatureExtractor,
    _attack_time_fraction,
    _delta_mfcc_statistics,
    _segment_wise_means,
)
from samplecore.storage.audio_store import NOMINAL_WAV_RATE


def _sine_wave(frame_count: int, *, channels: int = 1, frequency: float = 440.0) -> np.ndarray:
    times = np.arange(frame_count) / NOMINAL_WAV_RATE
    mono = np.sin(2.0 * np.pi * frequency * times)
    return np.tile(mono[:, None], (1, channels))


def _burst(frame_count: int, *, burst_length: int, at_start: bool) -> np.ndarray:
    mono = np.zeros(frame_count)
    burst = np.random.default_rng(0).normal(size=burst_length)
    if at_start:
        mono[:burst_length] = burst
    else:
        mono[-burst_length:] = burst
    return mono[:, None]


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


def test_extract_is_sensitive_to_the_position_of_a_transient() -> None:
    extractor = LibrosaFeatureExtractor()
    frame_count = NOMINAL_WAV_RATE
    burst_length = frame_count // 20

    early_vector = extractor.extract(_burst(frame_count, burst_length=burst_length, at_start=True))
    late_vector = extractor.extract(_burst(frame_count, burst_length=burst_length, at_start=False))

    assert not np.allclose(early_vector, late_vector)


def test_segment_wise_means_reports_one_mean_per_segment_in_order() -> None:
    rms = np.array([[1.0, 1.0, 1.0, 5.0, 5.0, 5.0, 9.0, 9.0, 9.0]])
    centroid = np.array([[2.0, 2.0, 2.0, 4.0, 4.0, 4.0, 6.0, 6.0, 6.0]])

    means = _segment_wise_means(rms, centroid)

    assert np.allclose(means, [1.0, 5.0, 9.0, 2.0, 4.0, 6.0])


def test_attack_time_fraction_is_near_zero_for_a_transient_at_the_start() -> None:
    frame_count = NOMINAL_WAV_RATE
    n_fft = min(2048, frame_count)
    mono = _burst(frame_count, burst_length=frame_count // 20, at_start=True)[:, 0]

    fraction = _attack_time_fraction(mono, sample_rate=NOMINAL_WAV_RATE, n_fft=n_fft, hop_length=n_fft // 4)

    assert fraction < 0.1


def test_attack_time_fraction_is_near_one_for_a_transient_at_the_end() -> None:
    frame_count = NOMINAL_WAV_RATE
    n_fft = min(2048, frame_count)
    mono = _burst(frame_count, burst_length=frame_count // 20, at_start=False)[:, 0]

    fraction = _attack_time_fraction(mono, sample_rate=NOMINAL_WAV_RATE, n_fft=n_fft, hop_length=n_fft // 4)

    assert fraction > 0.9


def test_attack_time_fraction_falls_back_to_the_default_for_silence() -> None:
    mono = np.zeros(NOMINAL_WAV_RATE)

    fraction = _attack_time_fraction(mono, sample_rate=NOMINAL_WAV_RATE, n_fft=2048, hop_length=512)

    assert fraction == NO_ONSET_ATTACK_FRACTION


def test_delta_mfcc_statistics_reports_zero_change_for_a_too_short_clip() -> None:
    mfcc = np.zeros((MFCC_COUNT, 2))

    statistics = _delta_mfcc_statistics(mfcc)

    assert np.array_equal(statistics, np.zeros(2 * MFCC_COUNT))


def test_delta_mfcc_statistics_is_near_zero_for_a_constant_coefficient_and_nonzero_for_a_moving_one() -> None:
    frame_count = 20
    constant_mfcc = np.tile(np.arange(MFCC_COUNT, dtype=float)[:, None], (1, frame_count))
    moving_mfcc = constant_mfcc.copy()
    moving_mfcc[0] = np.linspace(0.0, 10.0, frame_count)

    constant_statistics = _delta_mfcc_statistics(constant_mfcc)
    moving_statistics = _delta_mfcc_statistics(moving_mfcc)

    assert np.allclose(constant_statistics, 0.0, atol=1e-8)
    assert abs(moving_statistics[0]) > 1e-3
