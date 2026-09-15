from __future__ import annotations

from typing import Final

import numpy as np
import pytest

from samplemorph.measurement.morph_path.spectra import (
    blend_fit,
    crest_factor_db,
    fraction_spectrum,
    mean_peak_count,
    mean_spectral_entropy,
    resolved_spectrum,
)
from tests.samplemorph.conftest import harmonic_tone, noise_burst

FRAME_COUNT: Final[int] = 16384
CROSSFADE_WEIGHT: Final[float] = 0.3
PARTIAL_COUNT: Final[int] = 4
DISSOLVE_PEAK_RATIO_FLOOR: Final[float] = 1.6
SINE_CREST_DB: Final[float] = 20.0 * np.log10(np.sqrt(2.0))


def test_a_decibel_crossfade_of_two_spectra_is_fitted_exactly() -> None:
    first = fraction_spectrum(harmonic_tone(FRAME_COUNT, frequency=220.0)[:, 0])
    second = fraction_spectrum(noise_burst(FRAME_COUNT, seed=3)[:, 0])

    fit = blend_fit((1.0 - CROSSFADE_WEIGHT) * first + CROSSFADE_WEIGHT * second, first=first, second=second)

    assert fit.weight == pytest.approx(CROSSFADE_WEIGHT)
    assert fit.residual_share == pytest.approx(0.0, abs=1e-9)
    assert fit.endpoint_distance_db > 0.0


def test_identical_ends_leave_no_crossfade_to_tell_a_point_from() -> None:
    spectrum = fraction_spectrum(harmonic_tone(FRAME_COUNT, frequency=220.0)[:, 0])

    assert blend_fit(spectrum, first=spectrum, second=spectrum).residual_share == 0.0


def test_a_tone_reads_its_partials_and_two_tones_at_once_read_about_both() -> None:
    first = harmonic_tone(FRAME_COUNT, frequency=220.0)[:, 0]
    second = harmonic_tone(FRAME_COUNT, frequency=330.0)[:, 0]

    alone = mean_peak_count(resolved_spectrum(first))
    together = mean_peak_count(resolved_spectrum(first + second))

    assert alone == pytest.approx(PARTIAL_COUNT, abs=0.5)
    assert together / alone >= DISSOLVE_PEAK_RATIO_FLOOR


def test_noise_spreads_wider_than_a_tone() -> None:
    tone = mean_spectral_entropy(resolved_spectrum(harmonic_tone(FRAME_COUNT, frequency=220.0)[:, 0]))
    noise = mean_spectral_entropy(resolved_spectrum(noise_burst(FRAME_COUNT, seed=3)[:, 0]))

    assert noise > tone


def test_a_sine_reads_the_crest_factor_of_a_sine() -> None:
    sine = np.sin(2.0 * np.pi * 440.0 * np.arange(FRAME_COUNT) / 44100.0)

    assert crest_factor_db(sine) == pytest.approx(SINE_CREST_DB, abs=0.01)
