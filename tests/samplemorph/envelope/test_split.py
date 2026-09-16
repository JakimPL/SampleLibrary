from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.envelope.settings import EnvelopeSettings
from samplemorph.envelope.split import spectral_envelope, split_spectrum
from tests.samplemorph.transport.conftest import BIN_SPACING_HZ, CLIP_FRAMES, analysis_of, sines, tone

SETTINGS: Final[EnvelopeSettings] = EnvelopeSettings()
TONE_HZ: Final[float] = 300.0
BETWEEN_HZ: Final[float] = 450.0
RECONSTRUCTION_TOLERANCE: Final[float] = 1e-4
ENVELOPE_STEP_CEILING_DB: Final[float] = 3.0
EXCITATION_CONTRAST_FLOOR_DB: Final[float] = 20.0
FLAT_WITHIN_DB: Final[float] = 0.01
FLOOR_TOLERANCE_DB: Final[float] = 0.01


def _magnitude(mono: NDArray[np.float64]) -> NDArray[np.float32]:
    magnitude: NDArray[np.float32] = np.sqrt(analysis_of(mono).energy)
    return magnitude


def _decibels(values: NDArray[np.float32]) -> NDArray[np.float64]:
    return 20.0 * np.log10(np.maximum(values.astype(np.float64), np.finfo(np.float32).tiny))


def _bin(frequency_hz: float) -> int:
    return int(round(frequency_hz / BIN_SPACING_HZ))


def test_the_envelope_times_the_excitation_is_the_magnitude_again() -> None:
    magnitude = _magnitude(tone(TONE_HZ))

    split = split_spectrum(magnitude, settings=SETTINGS)

    np.testing.assert_allclose(split.envelope * split.excitation, magnitude, rtol=RECONSTRUCTION_TOLERANCE)


def test_the_envelope_is_smooth_where_the_magnitude_has_lobes() -> None:
    magnitude = _magnitude(tone(TONE_HZ))
    frame = magnitude.shape[1] // 2
    floored = np.maximum(magnitude[:, frame], magnitude.max() * 10.0 ** (-SETTINGS.floor_db / 20.0))

    envelope = spectral_envelope(magnitude, settings=SETTINGS)[:, frame]

    assert np.abs(np.diff(_decibels(envelope))).max() < ENVELOPE_STEP_CEILING_DB
    assert np.abs(np.diff(_decibels(floored))).max() > ENVELOPE_STEP_CEILING_DB


def test_the_excitation_keeps_the_partials_the_envelope_smoothed_over() -> None:
    magnitude = _magnitude(sines((TONE_HZ,)))
    frame = magnitude.shape[1] // 2

    excitation = _decibels(split_spectrum(magnitude, settings=SETTINGS).excitation[:, frame])

    assert excitation[_bin(TONE_HZ)] - excitation[_bin(BETWEEN_HZ)] > EXCITATION_CONTRAST_FLOOR_DB


def test_a_silent_frame_s_envelope_lies_flat_at_the_floor() -> None:
    magnitude = _magnitude(np.concatenate((tone(TONE_HZ, frame_count=CLIP_FRAMES // 2), np.zeros(CLIP_FRAMES // 2))))

    silent = _decibels(spectral_envelope(magnitude, settings=SETTINGS)[:, -1])

    assert np.ptp(silent) < FLAT_WITHIN_DB
    assert abs(silent.max() - (_decibels(magnitude.max(keepdims=True))[0] - SETTINGS.floor_db)) < FLOOR_TOLERANCE_DB
