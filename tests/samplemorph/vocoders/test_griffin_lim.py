from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from samplemorph.registries import CANONICALIZER_REGISTRY, SYNTHESIS_CANONICALIZER_NAMES
from samplemorph.vocoders.griffin_lim import GriffinLimVocoder, OraclePhaseVocoder
from tests.samplemorph.conftest import TEST_FRAME_COUNT, harmonic_tone

FAST_ITERATIONS = 4
TONE_FREQUENCY_HZ = 440.0


@dataclass(frozen=True)
class VocoderCase:
    """One registered frequency axis, synthesized back to audio through the shared vocoder."""

    name: str


VOCODER_CASES = tuple(VocoderCase(name=name) for name in sorted(CANONICALIZER_REGISTRY))
SYNTHESIS_CASES = tuple(VocoderCase(name=name) for name in sorted(SYNTHESIS_CANONICALIZER_NAMES))


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


@pytest.mark.parametrize("case", SYNTHESIS_CASES, ids=lambda case: case.name)
def test_a_synthesis_axis_lands_nearer_the_reference_than_unrelated_content_does(case: VocoderCase) -> None:
    """The property that makes an axis one audio is rendered from.

    Handed the source's own phase, a round trip through the axis reproduces that source. An axis
    that fails this returns something a listener hears as another sound, whatever its analysis
    accuracy, which is what confines `constant_q` to measurement.
    """
    canonicalizer = CANONICALIZER_REGISTRY[case.name]()
    tone = harmonic_tone(TEST_FRAME_COUNT, frequency=TONE_FREQUENCY_HZ)
    spectrogram = canonicalizer.restore(canonicalizer.canonicalize(tone))
    reference = tone[:, 0]
    unrelated = harmonic_tone(TEST_FRAME_COUNT, frequency=TONE_FREQUENCY_HZ * 3.0)[:, 0]

    oracle = OraclePhaseVocoder(reference).synthesize(spectrogram)

    assert _spectral_distance(reference, oracle) < _spectral_distance(reference, unrelated)


def test_the_constant_q_axis_is_kept_out_of_synthesis() -> None:
    """The measured reason `constant_q` stays an analysis axis, recorded so it stays recorded.

    Its bins measure amplitude per constant-Q band, which stands about 20 dB below the Fourier
    magnitude over the lowest octaves. A vocoder reads the difference as spectral shape, so even
    the source's own phase returns audio that sits as far from its original as unrelated content.
    """
    canonicalizer = CANONICALIZER_REGISTRY["constant_q"]()
    tone = harmonic_tone(TEST_FRAME_COUNT, frequency=TONE_FREQUENCY_HZ)
    spectrogram = canonicalizer.restore(canonicalizer.canonicalize(tone))
    reference = tone[:, 0]
    unrelated = harmonic_tone(TEST_FRAME_COUNT, frequency=TONE_FREQUENCY_HZ * 3.0)[:, 0]

    oracle = OraclePhaseVocoder(reference).synthesize(spectrogram)

    assert _spectral_distance(reference, oracle) > _spectral_distance(reference, unrelated)


def _spectral_distance(first: np.ndarray, second: np.ndarray) -> float:
    """Root-mean-square difference between two waveforms' log magnitude spectra."""
    width = min(first.shape[0], second.shape[0])
    first_spectrum = np.log1p(np.abs(np.fft.rfft(first[:width])))
    second_spectrum = np.log1p(np.abs(np.fft.rfft(second[:width])))
    return float(np.sqrt(np.mean((first_spectrum - second_spectrum) ** 2)))
