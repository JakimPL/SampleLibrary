from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.signal import resample_poly

from sampleextract.equivalence.fingerprint import (
    FREQUENCY_BANDS,
    TIME_BINS,
    compute_rate_fingerprint,
    compute_shape_fingerprint,
)

SAMPLE_RATE = 44100


def _tonal_waveform(frames: int) -> NDArray[np.float64]:
    time = np.arange(frames) / SAMPLE_RATE
    waveform = (
        0.5 * np.sin(2 * np.pi * 220 * time)
        + 0.3 * np.sin(2 * np.pi * 440 * time)
        + 0.2 * np.sin(2 * np.pi * 880 * time)
    )
    return waveform.reshape(-1, 1)


def test_compute_shape_fingerprint_returns_a_unit_norm_vector_of_the_declared_shape() -> None:
    fingerprint = compute_shape_fingerprint(_tonal_waveform(4410))

    assert fingerprint.shape == (TIME_BINS * FREQUENCY_BANDS,)
    assert np.isclose(np.linalg.norm(fingerprint), 1.0)


def test_compute_shape_fingerprint_returns_a_zero_vector_for_silence() -> None:
    silence = np.zeros((4410, 1))

    fingerprint = compute_shape_fingerprint(silence)

    assert np.array_equal(fingerprint, np.zeros(TIME_BINS * FREQUENCY_BANDS))


def test_the_shape_fingerprint_stays_similar_across_a_gain_and_a_trimmed_lead_in() -> None:
    original = _tonal_waveform(44100)

    reference = compute_shape_fingerprint(original)

    assert np.dot(reference, compute_shape_fingerprint(original * 0.3)) > 0.999
    assert np.dot(reference, compute_shape_fingerprint(original[64:])) > 0.99


def test_the_rate_fingerprint_stays_similar_across_a_resample() -> None:
    """A resample keeps every cycle a sound holds, which is what the rate fingerprint counts."""
    original = np.random.default_rng(7).standard_normal((20000, 1)) * np.exp(-np.arange(20000) / 4000)[:, np.newaxis]
    halved = resample_poly(original, up=1, down=2, axis=0)

    similarity = np.dot(compute_rate_fingerprint(original), compute_rate_fingerprint(halved))

    assert similarity > 0.97
    assert np.dot(compute_shape_fingerprint(original), compute_shape_fingerprint(halved)) < similarity


def test_a_short_waveform_is_read_padded_so_two_copies_of_it_lie_together() -> None:
    """A chip loop of a few dozen frames carries a fingerprint of its own, the same for a quieter copy."""
    short = _tonal_waveform(20)

    fingerprint = compute_shape_fingerprint(short)

    assert fingerprint.shape == (TIME_BINS * FREQUENCY_BANDS,)
    assert np.isclose(np.linalg.norm(fingerprint), 1.0)
    assert np.dot(fingerprint, compute_shape_fingerprint(short * 0.25)) > 0.999


def test_compute_shape_fingerprint_separates_unrelated_content() -> None:
    tonal = compute_shape_fingerprint(_tonal_waveform(22050))
    noise = compute_shape_fingerprint(np.random.default_rng(3).uniform(-1.0, 1.0, (22050, 1)))

    assert np.dot(tonal, noise) < 0.9


def test_the_rate_fingerprint_of_silence_is_the_zero_vector() -> None:
    assert np.array_equal(compute_rate_fingerprint(np.zeros((4410, 1))), np.zeros(TIME_BINS * FREQUENCY_BANDS))
