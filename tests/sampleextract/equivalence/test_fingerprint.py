from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.signal import resample_poly

from sampleextract.equivalence.fingerprint import FREQUENCY_BANDS, TIME_BINS, compute_fingerprint

SAMPLE_RATE = 44100


def _tonal_waveform(frames: int) -> NDArray[np.float64]:
    time = np.arange(frames) / SAMPLE_RATE
    waveform = (
        0.5 * np.sin(2 * np.pi * 220 * time)
        + 0.3 * np.sin(2 * np.pi * 440 * time)
        + 0.2 * np.sin(2 * np.pi * 880 * time)
    )
    return waveform.reshape(-1, 1)


def test_compute_fingerprint_returns_a_unit_norm_vector_of_the_declared_shape() -> None:
    fingerprint = compute_fingerprint(_tonal_waveform(4410))

    assert fingerprint.shape == (TIME_BINS * FREQUENCY_BANDS,)
    assert np.isclose(np.linalg.norm(fingerprint), 1.0)


def test_compute_fingerprint_returns_a_zero_vector_for_silence() -> None:
    silence = np.zeros((4410, 1))

    fingerprint = compute_fingerprint(silence)

    assert np.array_equal(fingerprint, np.zeros(TIME_BINS * FREQUENCY_BANDS))


def test_compute_fingerprint_stays_similar_across_resampling_and_a_trimmed_lead_in() -> None:
    original = _tonal_waveform(44100)
    resampled = resample_poly(original, up=22050, down=44100, axis=0)
    trimmed = resampled[64:]

    reference = compute_fingerprint(original)
    untrimmed_similarity = np.dot(reference, compute_fingerprint(resampled))
    trimmed_similarity = np.dot(reference, compute_fingerprint(trimmed))

    assert untrimmed_similarity > 0.99
    assert trimmed_similarity > 0.99


def test_compute_fingerprint_handles_a_waveform_too_short_for_every_time_bin_to_carry_a_spectrum() -> None:
    """A waveform with far fewer frames than TIME_BINS leaves some bins with too few samples for
    a meaningful spectrum -- those bins contribute zero energy rather than raising.
    """
    fingerprint = compute_fingerprint(_tonal_waveform(20))

    assert fingerprint.shape == (TIME_BINS * FREQUENCY_BANDS,)


def test_compute_fingerprint_separates_unrelated_content() -> None:
    tonal = compute_fingerprint(_tonal_waveform(22050))
    noise = compute_fingerprint(np.random.default_rng(3).uniform(-1.0, 1.0, (22050, 1)))

    assert np.dot(tonal, noise) < 0.9
