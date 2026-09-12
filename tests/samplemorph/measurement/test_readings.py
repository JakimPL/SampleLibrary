from __future__ import annotations

import numpy as np
import pytest

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.measurement.readings import read_reconstruction

TONE_SECONDS = 1.0
TONE_HZ = 440.0
PEAK = 0.5
PEAK_DBFS = -6.02
ZERO_TOLERANCE = 1e-6
PEAK_TOLERANCE_DB = 0.01


def _tone() -> np.ndarray:
    times = np.arange(int(TONE_SECONDS * NOMINAL_WAV_RATE)) / NOMINAL_WAV_RATE
    return PEAK * np.sin(2.0 * np.pi * TONE_HZ * times)


def test_a_waveform_against_itself_reads_zero_on_every_distance_and_its_own_peak() -> None:
    pytest.importorskip("pyloudnorm")
    tone = _tone()

    readings = read_reconstruction(tone, tone)

    assert readings.held_out_db == pytest.approx(0.0, abs=ZERO_TOLERANCE)
    assert readings.loudness_delta_lu == pytest.approx(0.0, abs=ZERO_TOLERANCE)
    assert readings.gated
    assert readings.fluctuation_excess == pytest.approx(0.0, abs=ZERO_TOLERANCE)
    assert readings.roughness_excess == pytest.approx(0.0, abs=ZERO_TOLERANCE)
    assert readings.modulation_distance == pytest.approx(0.0, abs=ZERO_TOLERANCE)
    assert readings.modulation_excess == pytest.approx(0.0, abs=ZERO_TOLERANCE)
    assert readings.peak_dbfs == pytest.approx(PEAK_DBFS, abs=PEAK_TOLERANCE_DB)


def test_a_quieter_reconstruction_reads_a_negative_delta_and_a_lower_peak() -> None:
    pytest.importorskip("pyloudnorm")
    tone = _tone()

    readings = read_reconstruction(tone / 2.0, tone)

    assert readings.loudness_delta_lu < 0.0
    assert readings.peak_dbfs < PEAK_DBFS
