from __future__ import annotations

import numpy as np

from samplecloud.backends.invariant_backend import (
    ENVELOPE_POINTS,
    NUMBER_COEFFICIENTS,
    SPECTRAL_TIME_POINTS,
    InvariantFeatureExtractor,
    _hann_kernel,
)
from samplecore.storage.audio_store import NOMINAL_WAV_RATE

EXPECTED_VECTOR_LENGTH = ENVELOPE_POINTS + NUMBER_COEFFICIENTS * SPECTRAL_TIME_POINTS


def _tone(frame_count: int, *, frequency: float, harmonics: tuple[float, ...] = (1.0, 0.5, 0.25)) -> np.ndarray:
    """A stationary, band-limited tone built from a fixed harmonic template -- two tones built from
    the same template at different frequencies are genuinely the same "instrument" at a different
    pitch, not two arbitrary unrelated sounds.
    """
    times = np.arange(frame_count) / NOMINAL_WAV_RATE
    mono = np.zeros(frame_count)
    for harmonic_index, weight in enumerate(harmonics, start=1):
        mono += weight * np.sin(2 * np.pi * frequency * harmonic_index * times)
    return mono[:, None]


def _noise_burst(frame_count: int, *, seed: int = 0) -> np.ndarray:
    """A short, fast-decaying noise transient -- percussive, with no fundamental frequency at all."""
    envelope = np.exp(-np.linspace(0.0, 8.0, frame_count))
    noise = np.random.default_rng(seed).normal(size=frame_count)
    return (envelope * noise)[:, None]


def test_extract_returns_a_finite_fixed_length_vector() -> None:
    extractor = InvariantFeatureExtractor()

    vector = extractor.extract(_tone(NOMINAL_WAV_RATE, frequency=440.0))

    assert vector.shape == (EXPECTED_VECTOR_LENGTH,)
    assert np.all(np.isfinite(vector))


def test_extract_returns_the_same_length_regardless_of_input_length() -> None:
    extractor = InvariantFeatureExtractor()

    short_vector = extractor.extract(_tone(2048, frequency=440.0))
    long_vector = extractor.extract(_tone(5 * NOMINAL_WAV_RATE, frequency=440.0))

    assert short_vector.shape == long_vector.shape


def test_extract_handles_stereo_input() -> None:
    extractor = InvariantFeatureExtractor()
    mono = _tone(NOMINAL_WAV_RATE, frequency=440.0)

    vector = extractor.extract(np.tile(mono, (1, 2)))

    assert np.all(np.isfinite(vector))


def test_extract_handles_a_percussive_noise_burst_without_error() -> None:
    """No fundamental to detect, and none needed: a noise burst takes the same code path as a
    genuinely pitched tone, uniformly.
    """
    extractor = InvariantFeatureExtractor()

    vector = extractor.extract(_noise_burst(2048))

    assert np.all(np.isfinite(vector))


def test_extract_is_approximately_invariant_to_gain() -> None:
    extractor = InvariantFeatureExtractor()
    tone = _tone(NOMINAL_WAV_RATE, frequency=330.0)

    original_vector = extractor.extract(tone)
    quiet_vector = extractor.extract(tone * 0.25)

    assert np.linalg.norm(original_vector - quiet_vector) < 0.05


def test_extract_lands_closer_for_a_transposed_tone_than_for_unrelated_content() -> None:
    """The same harmonic template at two genuinely different fundamental frequencies -- the same
    tracker instrument played at two different notes -- lands closer together than either does to a
    percussive noise burst, the real invariance property this backend exists to provide.
    """
    extractor = InvariantFeatureExtractor()
    low_note = _tone(NOMINAL_WAV_RATE, frequency=220.0)
    high_note = _tone(NOMINAL_WAV_RATE, frequency=660.0)
    unrelated = _noise_burst(NOMINAL_WAV_RATE)

    low_vector = extractor.extract(low_note)
    high_vector = extractor.extract(high_note)
    unrelated_vector = extractor.extract(unrelated)

    transposed_distance = np.linalg.norm(low_vector - high_vector)
    unrelated_distance = np.linalg.norm(low_vector - unrelated_vector)
    assert transposed_distance < unrelated_distance


def test_hann_kernel_sums_to_one_and_is_symmetric() -> None:
    kernel = _hann_kernel(64)

    assert np.isclose(kernel.sum(), 1.0)
    assert np.allclose(kernel, kernel[::-1])
