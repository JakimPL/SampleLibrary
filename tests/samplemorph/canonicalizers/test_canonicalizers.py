from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from samplemorph.canonicalizers import Canonicalizer
from samplemorph.registries import CANONICALIZER_REGISTRY
from tests.samplemorph.conftest import TEST_FRAME_COUNT, harmonic_tone, noise_burst

GAIN_FACTOR = 0.25
GAIN_FACTOR_IN_OCTAVES = -2.0
RESAMPLING_INVARIANT_TOLERANCE_SEMITONES = 1.0


@dataclass(frozen=True)
class CanonicalizerCase:
    """One registered frequency axis, exercised through the shared canonicalizer contract."""

    name: str

    def build(self) -> Canonicalizer:
        return CANONICALIZER_REGISTRY[self.name]()


CANONICALIZER_CASES = tuple(CanonicalizerCase(name=name) for name in sorted(CANONICALIZER_REGISTRY))


@pytest.mark.parametrize("case", CANONICALIZER_CASES, ids=lambda case: case.name)
def test_canonicalize_returns_the_geometry_grid_shape(case: CanonicalizerCase) -> None:
    canonicalizer = case.build()

    image = canonicalizer.canonicalize(harmonic_tone(TEST_FRAME_COUNT, frequency=440.0))

    assert image.grid.shape == canonicalizer.geometry.grid_shape


@pytest.mark.parametrize("case", CANONICALIZER_CASES, ids=lambda case: case.name)
def test_canonicalize_returns_one_shape_whatever_the_input_length(case: CanonicalizerCase) -> None:
    canonicalizer = case.build()

    short = canonicalizer.canonicalize(harmonic_tone(2048, frequency=440.0))
    long = canonicalizer.canonicalize(harmonic_tone(16 * 2048, frequency=440.0))

    assert short.grid.shape == long.grid.shape


@pytest.mark.parametrize("case", CANONICALIZER_CASES, ids=lambda case: case.name)
def test_canonicalize_keeps_the_grid_finite_and_within_the_unit_range(case: CanonicalizerCase) -> None:
    canonicalizer = case.build()

    image = canonicalizer.canonicalize(harmonic_tone(TEST_FRAME_COUNT, frequency=220.0))

    assert np.all(np.isfinite(image.grid))
    assert image.grid.min() >= 0.0
    assert image.grid.max() <= 1.0


@pytest.mark.parametrize("case", CANONICALIZER_CASES, ids=lambda case: case.name)
def test_canonicalize_handles_a_percussive_noise_burst(case: CanonicalizerCase) -> None:
    """A burst with no fundamental takes the same path a pitched tone does, uniformly."""
    canonicalizer = case.build()

    image = canonicalizer.canonicalize(noise_burst(2048, seed=0))

    assert np.all(np.isfinite(image.grid))


@pytest.mark.parametrize("case", CANONICALIZER_CASES, ids=lambda case: case.name)
def test_a_gain_change_leaves_the_grid_alone_and_moves_only_the_recorded_gain(case: CanonicalizerCase) -> None:
    """Level is a mixing decision, so it belongs in the conditioners rather than in the picture."""
    canonicalizer = case.build()
    tone = harmonic_tone(TEST_FRAME_COUNT, frequency=330.0)

    loud = canonicalizer.canonicalize(tone)
    quiet = canonicalizer.canonicalize(tone * GAIN_FACTOR)

    assert np.allclose(loud.grid, quiet.grid)
    assert quiet.conditioners.log_gain == pytest.approx(loud.conditioners.log_gain + GAIN_FACTOR_IN_OCTAVES, abs=1e-6)


@pytest.mark.parametrize("case", CANONICALIZER_CASES, ids=lambda case: case.name)
def test_the_recorded_duration_follows_the_frame_count(case: CanonicalizerCase) -> None:
    canonicalizer = case.build()

    shorter = canonicalizer.canonicalize(harmonic_tone(TEST_FRAME_COUNT, frequency=440.0))
    longer = canonicalizer.canonicalize(harmonic_tone(2 * TEST_FRAME_COUNT, frequency=440.0))

    assert longer.conditioners.log_duration == pytest.approx(shorter.conditioners.log_duration + 1.0)


@pytest.mark.parametrize("case", CANONICALIZER_CASES, ids=lambda case: case.name)
def test_restore_returns_a_spectrogram_sounding_for_the_recorded_duration(case: CanonicalizerCase) -> None:
    canonicalizer = case.build()
    image = canonicalizer.canonicalize(harmonic_tone(TEST_FRAME_COUNT, frequency=440.0))

    spectrogram = canonicalizer.restore(image)

    assert spectrogram.frame_count == pytest.approx(TEST_FRAME_COUNT, rel=0.01)
    assert np.all(np.isfinite(spectrogram.magnitude))


@pytest.mark.parametrize("case", CANONICALIZER_CASES, ids=lambda case: case.name)
def test_restoring_an_unmodified_image_recovers_the_peak_magnitude(case: CanonicalizerCase) -> None:
    """The gain the grid was normalized by comes back, so a reconstruction sits at its own level."""
    canonicalizer = case.build()
    image = canonicalizer.canonicalize(harmonic_tone(TEST_FRAME_COUNT, frequency=440.0))

    spectrogram = canonicalizer.restore(image)

    assert float(spectrogram.magnitude.max()) == pytest.approx(2.0**image.conditioners.log_gain, rel=0.05)


@pytest.mark.parametrize("case", CANONICALIZER_CASES, ids=lambda case: case.name)
def test_a_transposed_tone_lands_closer_than_unrelated_content(case: CanonicalizerCase) -> None:
    """Aligning the picture is what makes one instrument at two pitches read as one instrument."""
    canonicalizer = case.build()

    low = canonicalizer.canonicalize(harmonic_tone(TEST_FRAME_COUNT, frequency=220.0))
    high = canonicalizer.canonicalize(harmonic_tone(TEST_FRAME_COUNT, frequency=440.0))
    unrelated = canonicalizer.canonicalize(noise_burst(TEST_FRAME_COUNT, seed=1))

    transposed_distance = float(np.sqrt(np.mean((low.grid - high.grid) ** 2)))
    unrelated_distance = float(np.sqrt(np.mean((low.grid - unrelated.grid) ** 2)))
    assert transposed_distance < unrelated_distance
