from __future__ import annotations

import numpy as np
import pytest

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.canonicalizers.log_frequency import LogFrequencyCanonicalizer
from samplemorph.canonicalizers.mel import build_mel_canonicalizer
from samplemorph.geometry import AnalysisWindow, analysis_taper, log_frequency_geometry
from samplemorph.measurement.loudness import loudness_delta
from samplemorph.measurement.modulation_spectrum import modulation_spectrum_distance
from samplemorph.registries import PGHI_VOCODER_NAME, VOCODER_REGISTRY
from samplemorph.vocoders.pghi import PghiVocoder
from tests.samplemorph.conftest import TEST_FRAME_COUNT, harmonic_tone

TONE_FREQUENCY_HZ = 330.0
LOUDNESS_TOLERANCE_LU = 1.0
# The integrated phase reads about 0.03 of modulation distance on a held tone, where the source's
# own phase reads under 0.003 and an iterated estimate read 0.25 on the same rung of the ladder.
TONE_FLUTTER_CEILING = 0.05


def _gaussian_canonicalizer() -> LogFrequencyCanonicalizer:
    return LogFrequencyCanonicalizer(log_frequency_geometry(analysis_window=AnalysisWindow.GAUSSIAN))


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


def test_the_integrated_phase_makes_a_tone_audible_close_to_its_level() -> None:
    canonicalizer = _gaussian_canonicalizer()
    tone = harmonic_tone(4 * TEST_FRAME_COUNT, frequency=TONE_FREQUENCY_HZ)[:, 0]
    spectrogram = canonicalizer.restore(canonicalizer.canonicalize(prepare_mono(tone)))

    reconstruction = PghiVocoder().synthesize(spectrogram)

    assert reconstruction.shape == tone.shape
    assert np.isfinite(reconstruction).all()
    assert abs(loudness_delta(reconstruction, tone, source_rate_hz=NOMINAL_WAV_RATE).delta_lu) < LOUDNESS_TOLERANCE_LU


def test_the_integrated_phase_holds_a_tone_steady() -> None:
    canonicalizer = _gaussian_canonicalizer()
    tone = harmonic_tone(4 * TEST_FRAME_COUNT, frequency=TONE_FREQUENCY_HZ)[:, 0]
    spectrogram = canonicalizer.restore(canonicalizer.canonicalize(prepare_mono(tone)))

    integrated = modulation_spectrum_distance(PghiVocoder().synthesize(spectrogram), tone)

    assert integrated.distance < TONE_FLUTTER_CEILING


def test_a_hann_analysis_is_refused_by_name() -> None:
    canonicalizer = LogFrequencyCanonicalizer(log_frequency_geometry(analysis_window=AnalysisWindow.HANN))
    spectrogram = canonicalizer.restore(
        canonicalizer.canonicalize(prepare_mono(harmonic_tone(TEST_FRAME_COUNT, frequency=TONE_FREQUENCY_HZ)[:, 0]))
    )

    with pytest.raises(ValueError, match="hann taper"):
        PghiVocoder().synthesize(spectrogram)


def test_another_axis_is_refused_by_name() -> None:
    canonicalizer = build_mel_canonicalizer()
    spectrogram = canonicalizer.restore(
        canonicalizer.canonicalize(prepare_mono(harmonic_tone(TEST_FRAME_COUNT, frequency=TONE_FREQUENCY_HZ)[:, 0]))
    )

    with pytest.raises(ValueError, match="is a mel one"):
        PghiVocoder().synthesize(spectrogram)


def test_the_registry_builds_the_vocoder_by_name() -> None:
    assert isinstance(VOCODER_REGISTRY[PGHI_VOCODER_NAME](), PghiVocoder)
