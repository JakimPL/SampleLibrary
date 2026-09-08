from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from samplemorph.registries import CANONICALIZER_REGISTRY
from samplemorph.vocoders.griffin_lim import GriffinLimVocoder, OraclePhaseVocoder
from tests.samplemorph.conftest import TEST_FRAME_COUNT, harmonic_tone

FAST_ITERATIONS = 4
TONE_FREQUENCY_HZ = 440.0


@dataclass(frozen=True)
class VocoderCase:
    """One registered frequency axis, synthesized back to audio through the shared vocoder."""

    name: str


VOCODER_CASES = tuple(VocoderCase(name=name) for name in sorted(CANONICALIZER_REGISTRY))


@pytest.mark.parametrize("case", VOCODER_CASES, ids=lambda case: case.name)
def test_synthesize_returns_the_frame_count_the_spectrogram_asks_for(case: VocoderCase) -> None:
    canonicalizer = CANONICALIZER_REGISTRY[case.name]()
    image = canonicalizer.canonicalize(harmonic_tone(TEST_FRAME_COUNT, frequency=TONE_FREQUENCY_HZ))
    spectrogram = canonicalizer.restore(image)

    waveform = GriffinLimVocoder(iterations=FAST_ITERATIONS).synthesize(spectrogram)

    assert waveform.shape == (spectrogram.frame_count,)
    assert np.all(np.isfinite(waveform))


@pytest.mark.parametrize("case", VOCODER_CASES, ids=lambda case: case.name)
def test_synthesize_produces_audible_content_rather_than_silence(case: VocoderCase) -> None:
    canonicalizer = CANONICALIZER_REGISTRY[case.name]()
    image = canonicalizer.canonicalize(harmonic_tone(TEST_FRAME_COUNT, frequency=TONE_FREQUENCY_HZ))

    waveform = GriffinLimVocoder(iterations=FAST_ITERATIONS).synthesize(canonicalizer.restore(image))

    assert float(np.abs(waveform).max()) > 0.0


@pytest.mark.parametrize("case", VOCODER_CASES, ids=lambda case: case.name)
def test_the_oracle_vocoder_lands_nearer_the_reference_than_unrelated_content_does(case: VocoderCase) -> None:
    """Reusing the source's own phase reconstructs that source, which is what makes it a yardstick.

    The comparison against the phase estimate belongs to the measurement pass rather than here: how
    much the estimate costs varies by frequency axis, and on an axis whose magnitude mapping is
    itself lossy the true phase arrives paired with a magnitude it no longer matches.
    """
    canonicalizer = CANONICALIZER_REGISTRY[case.name]()
    tone = harmonic_tone(TEST_FRAME_COUNT, frequency=TONE_FREQUENCY_HZ)
    spectrogram = canonicalizer.restore(canonicalizer.canonicalize(tone))
    reference = tone[:, 0]
    unrelated = harmonic_tone(TEST_FRAME_COUNT, frequency=TONE_FREQUENCY_HZ * 3.0)[:, 0]

    oracle = OraclePhaseVocoder(reference).synthesize(spectrogram)

    assert _spectral_distance(reference, oracle) < _spectral_distance(reference, unrelated)


def _spectral_distance(first: np.ndarray, second: np.ndarray) -> float:
    """Root-mean-square difference between two waveforms' log magnitude spectra."""
    width = min(first.shape[0], second.shape[0])
    first_spectrum = np.log1p(np.abs(np.fft.rfft(first[:width])))
    second_spectrum = np.log1p(np.abs(np.fft.rfft(second[:width])))
    return float(np.sqrt(np.mean((first_spectrum - second_spectrum) ** 2)))
