from __future__ import annotations

import librosa
import numpy as np

from samplemorph.canonicalizers.common import bands_onto_linear_axis
from samplemorph.canonicalizers.linear_axis import onto_linear_axis
from samplemorph.canonicalizers.log_frequency import band_weights, linear_axis_inverse
from samplemorph.geometry import log_frequency_geometry
from tests.samplemorph.conftest import TEST_FRAME_COUNT, harmonic_tone

TONE_FREQUENCY_HZ = 220.0
RANDOM_SEED = 4
FRAME_COUNT = 6


def _tone_magnitude() -> np.ndarray:
    geometry = log_frequency_geometry()
    tone = harmonic_tone(4 * TEST_FRAME_COUNT, frequency=TONE_FREQUENCY_HZ)[:, 0]
    return np.abs(librosa.stft(tone, n_fft=geometry.fft_length, hop_length=geometry.hop_length))


def test_the_inverse_reproduces_the_bands_a_magnitude_was_read_into() -> None:
    geometry = log_frequency_geometry()
    weights = band_weights(geometry)
    linear = np.random.default_rng(RANDOM_SEED).random((weights.shape[1], FRAME_COUNT))
    bands = weights @ linear

    reproduced = weights @ (linear_axis_inverse(geometry) @ bands)

    np.testing.assert_allclose(reproduced, bands, atol=1e-8)


def test_the_reading_stays_a_magnitude_and_leaves_bins_no_band_touches_silent() -> None:
    geometry = log_frequency_geometry()
    bands = np.ones((geometry.band_count, FRAME_COUNT))

    linear = onto_linear_axis(bands, geometry=geometry)

    untouched = band_weights(geometry).sum(axis=0) == 0.0
    assert np.all(linear >= 0.0)
    assert untouched.sum() > 0
    assert np.array_equal(linear[untouched], np.zeros((int(untouched.sum()), FRAME_COUNT)))


def test_the_least_squares_reading_recovers_a_tone_closer_than_interpolation() -> None:
    geometry = log_frequency_geometry()
    magnitude = _tone_magnitude()
    bands = band_weights(geometry) @ magnitude

    least_squares = onto_linear_axis(bands, geometry=geometry)
    interpolated = bands_onto_linear_axis(
        bands, band_frequencies=geometry.band_frequencies, linear_frequencies=geometry.linear_frequencies
    )

    assert np.linalg.norm(least_squares - magnitude) < np.linalg.norm(interpolated - magnitude)


def test_the_inverse_is_designed_once_per_geometry() -> None:
    geometry = log_frequency_geometry()

    assert linear_axis_inverse(geometry) is linear_axis_inverse(log_frequency_geometry())
