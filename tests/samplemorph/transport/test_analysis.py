from __future__ import annotations

import numpy as np
import pytest

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.transport.settings import TransportSettings
from tests.samplemorph.transport.conftest import GEOMETRY, analysis_of, decaying, tone

ONSET_TOLERANCE_SECONDS = 0.02


def test_an_analysis_holds_the_frames_and_totals_of_its_sound() -> None:
    analysis = analysis_of(tone(440.0))

    assert analysis.energy.shape == (GEOMETRY.fft_length // 2 + 1, 1 + analysis.sample_count // GEOMETRY.hop_length)
    assert analysis.energy.dtype == np.float32
    assert np.allclose(analysis.frame_energy, analysis.energy.sum(axis=0))
    assert analysis.silent_shape.sum() == pytest.approx(1.0, rel=1e-5)
    assert analysis.outline.shape == analysis.energy.shape
    assert analysis.nbytes > analysis.energy.nbytes


def test_a_silent_sound_spreads_its_shape_evenly() -> None:
    analysis = analysis_of(np.zeros(4096))

    assert np.allclose(analysis.silent_shape, 1.0 / analysis.silent_shape.shape[0])


def test_an_analysis_places_its_onset_at_the_strike() -> None:
    delay_seconds = 0.12

    analysis = analysis_of(decaying(tone(440.0), time_constant_seconds=0.05, delay_seconds=delay_seconds))

    assert analysis.onset_sample / NOMINAL_WAV_RATE == pytest.approx(delay_seconds, abs=ONSET_TOLERANCE_SECONDS)


def test_settings_refuse_an_empty_uniform_share() -> None:
    with pytest.raises(ValueError):
        TransportSettings(uniform_share=0.0)
