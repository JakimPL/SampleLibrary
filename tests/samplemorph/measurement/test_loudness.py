from __future__ import annotations

import numpy as np
import pytest
from scipy.signal import hilbert

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.measurement.loudness import integrated_loudness, loudness_delta, match_loudness
from samplemorph.rendering import HEADROOM

TONE_SECONDS = 1.0
SHORT_CLIP_SECONDS = 0.2
REFERENCE_TONE_HZ = 1000.0
REFERENCE_PEAK_DBFS = -23.0
REFERENCE_MONO_LUFS = -26.0
LOUDNESS_TOLERANCE_LU = 0.1
HALF_AMPLITUDE_LU = -6.02
GAIN_TOLERANCE_LU = 0.05
INVARIANCE_LU = 0.05
MATCHED_PEAK = 0.98
CLICK_SPACING_SAMPLES = 2205


def _reference_tone() -> np.ndarray:
    times = np.arange(int(TONE_SECONDS * NOMINAL_WAV_RATE)) / NOMINAL_WAV_RATE
    return 10.0 ** (REFERENCE_PEAK_DBFS / 20.0) * np.sin(2.0 * np.pi * REFERENCE_TONE_HZ * times)


def test_the_broadcast_reference_tone_reads_the_standard_loudness() -> None:
    pytest.importorskip("pyloudnorm")
    tone = _reference_tone()

    reading = loudness_delta(tone, tone)

    assert reading.reference_lufs == pytest.approx(REFERENCE_MONO_LUFS, abs=LOUDNESS_TOLERANCE_LU)
    assert reading.delta_lu == pytest.approx(0.0, abs=GAIN_TOLERANCE_LU)
    assert reading.gated


def test_a_reconstruction_at_half_amplitude_reads_six_lu_quieter() -> None:
    pytest.importorskip("pyloudnorm")
    tone = _reference_tone()

    reading = loudness_delta(tone / 2.0, tone)

    assert reading.delta_lu == pytest.approx(HALF_AMPLITUDE_LU, abs=GAIN_TOLERANCE_LU)


def test_peak_matched_signals_of_different_density_read_a_delta() -> None:
    pytest.importorskip("pyloudnorm")
    tone = _reference_tone()
    sine = MATCHED_PEAK * tone / np.abs(tone).max()
    clicks = np.zeros_like(tone)
    clicks[::CLICK_SPACING_SAMPLES] = MATCHED_PEAK

    reading = loudness_delta(clicks, sine)

    assert reading.delta_lu < 0.0


def test_a_pair_shorter_than_one_gating_block_reads_through_the_whole_clip_path() -> None:
    pytest.importorskip("pyloudnorm")
    tone = _reference_tone()[: int(SHORT_CLIP_SECONDS * NOMINAL_WAV_RATE)]

    reading = loudness_delta(tone / 2.0, tone)

    assert reading.gated is False
    assert reading.delta_lu == pytest.approx(HALF_AMPLITUDE_LU, abs=GAIN_TOLERANCE_LU)
    assert reading.reference_lufs == pytest.approx(REFERENCE_MONO_LUFS, abs=LOUDNESS_TOLERANCE_LU)


def test_a_global_phase_shift_reads_no_change_in_loudness() -> None:
    pytest.importorskip("pyloudnorm")
    tone = _reference_tone()

    reading = loudness_delta(np.imag(hilbert(tone)), tone)

    assert reading.delta_lu == pytest.approx(0.0, abs=INVARIANCE_LU)


def test_an_empty_pair_says_so() -> None:
    pytest.importorskip("pyloudnorm")

    with pytest.raises(ValueError, match="empty waveform"):
        loudness_delta(np.zeros(0), np.zeros(0))


def test_matching_brings_a_quieter_copy_to_the_reference_and_the_set_under_the_headroom() -> None:
    pytest.importorskip("pyloudnorm")
    tone = _reference_tone()

    matched_tone, matched_copy = match_loudness((tone, tone / 4.0), reference=tone)

    assert integrated_loudness(matched_copy) == pytest.approx(integrated_loudness(matched_tone), abs=GAIN_TOLERANCE_LU)
    assert max(np.abs(matched_tone).max(), np.abs(matched_copy).max()) == pytest.approx(HEADROOM)
    assert np.allclose(matched_tone, matched_copy)


def test_matching_leaves_silence_silent() -> None:
    pytest.importorskip("pyloudnorm")
    tone = _reference_tone()

    _, silence = match_loudness((tone, np.zeros_like(tone)), reference=tone)

    assert not np.any(silence)
