from __future__ import annotations

import numpy as np
import pytest

from samplemorph.canonicalizers.common import analysis_transform, prepare_mono
from samplemorph.geometry import AnalysisWindow, analysis_taper, log_frequency_geometry
from samplemorph.vocoders.pghi import integrate_and_synthesize
from tests.samplemorph.conftest import TEST_FRAME_COUNT, harmonic_tone

TONE_FREQUENCY_HZ = 330.0
LEVEL_TOLERANCE_DB = 1.0


def test_the_gaussian_taper_peaks_at_the_frame_center_and_falls_to_the_edge_level() -> None:
    geometry = log_frequency_geometry(analysis_window=AnalysisWindow.GAUSSIAN)

    taper = analysis_taper(geometry)

    assert taper.shape == (geometry.fft_length,)
    assert taper.max() == pytest.approx(1.0, abs=1e-6)
    assert int(np.argmax(taper)) in (geometry.fft_length // 2 - 1, geometry.fft_length // 2)
    assert taper[0] < 0.02


def test_the_hann_taper_is_the_periodic_one_the_analysis_overlaps_cleanly() -> None:
    geometry = log_frequency_geometry(analysis_window=AnalysisWindow.HANN)

    taper = analysis_taper(geometry)

    assert taper.shape == (geometry.fft_length,)
    assert taper[0] == pytest.approx(0.0)
    assert taper.max() == pytest.approx(1.0)


def test_the_integrated_phase_makes_a_tone_audible_at_its_own_length_and_level() -> None:
    geometry = log_frequency_geometry(analysis_window=AnalysisWindow.GAUSSIAN)
    tone = prepare_mono(harmonic_tone(4 * TEST_FRAME_COUNT, frequency=TONE_FREQUENCY_HZ)[:, 0])
    magnitude = np.abs(analysis_transform(tone, geometry=geometry))

    reconstruction = integrate_and_synthesize(magnitude, geometry=geometry, frame_count=tone.shape[0])

    level_delta_db = 20.0 * np.log10(np.sqrt(np.mean(reconstruction**2)) / np.sqrt(np.mean(tone**2)))
    assert reconstruction.shape == tone.shape
    assert np.isfinite(reconstruction).all()
    assert abs(level_delta_db) < LEVEL_TOLERANCE_DB
