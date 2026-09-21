from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pytest

from sampledescriptor.canonicalizers import Canonicalizer
from sampledescriptor.canonicalizers.log_frequency import band_weights, to_sound_image
from sampledescriptor.geometry import Anchor, grid_geometry
from sampledescriptor.registries import CANONICALIZER_REGISTRY
from samplemorph.canonicalizers.common import analysis_transform, prepare_mono
from samplemorph.geometry import log_frequency_geometry
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

    image = canonicalizer.canonicalize(prepare_mono(harmonic_tone(TEST_FRAME_COUNT, frequency=440.0)))

    assert image.grid.shape == canonicalizer.geometry.grid_shape


@pytest.mark.parametrize("case", CANONICALIZER_CASES, ids=lambda case: case.name)
def test_canonicalize_returns_one_shape_whatever_the_input_length(case: CanonicalizerCase) -> None:
    canonicalizer = case.build()

    short = canonicalizer.canonicalize(prepare_mono(harmonic_tone(2048, frequency=440.0)))
    long = canonicalizer.canonicalize(prepare_mono(harmonic_tone(16 * 2048, frequency=440.0)))

    assert short.grid.shape == long.grid.shape


def test_a_hit_shorter_than_one_transform_is_analyzed_without_a_warning() -> None:
    geometry = grid_geometry()
    hit = np.zeros(geometry.fft_length // 4)
    hit[0] = 1.0

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        transform = analysis_transform(hit, geometry=geometry)

    assert transform.shape == (geometry.fft_length // 2 + 1, 1 + hit.shape[0] // geometry.hop_length)


@pytest.mark.parametrize("case", CANONICALIZER_CASES, ids=lambda case: case.name)
def test_canonicalize_keeps_the_grid_finite_and_within_the_unit_range(case: CanonicalizerCase) -> None:
    canonicalizer = case.build()

    image = canonicalizer.canonicalize(prepare_mono(harmonic_tone(TEST_FRAME_COUNT, frequency=220.0)))

    assert np.all(np.isfinite(image.grid))
    assert image.grid.min() >= 0.0
    assert image.grid.max() <= 1.0


@pytest.mark.parametrize("case", CANONICALIZER_CASES, ids=lambda case: case.name)
def test_canonicalize_handles_a_percussive_noise_burst(case: CanonicalizerCase) -> None:
    """A burst with no fundamental takes the same path a pitched tone does, uniformly."""
    canonicalizer = case.build()

    image = canonicalizer.canonicalize(prepare_mono(noise_burst(2048, seed=0)))

    assert np.all(np.isfinite(image.grid))


@pytest.mark.parametrize("case", CANONICALIZER_CASES, ids=lambda case: case.name)
def test_a_gain_change_leaves_the_grid_alone_and_moves_only_the_recorded_gain(case: CanonicalizerCase) -> None:
    """Level is a mixing decision, so it belongs in the conditioners rather than in the picture."""
    canonicalizer = case.build()
    tone = harmonic_tone(TEST_FRAME_COUNT, frequency=330.0)

    loud = canonicalizer.canonicalize(prepare_mono(tone))
    quiet = canonicalizer.canonicalize(prepare_mono(tone * GAIN_FACTOR))

    assert np.allclose(loud.grid, quiet.grid)
    assert quiet.conditioners.log_gain == pytest.approx(loud.conditioners.log_gain + GAIN_FACTOR_IN_OCTAVES, abs=1e-6)


@pytest.mark.parametrize("case", CANONICALIZER_CASES, ids=lambda case: case.name)
def test_the_recorded_duration_follows_the_frame_count(case: CanonicalizerCase) -> None:
    canonicalizer = case.build()

    shorter = canonicalizer.canonicalize(prepare_mono(harmonic_tone(TEST_FRAME_COUNT, frequency=440.0)))
    longer = canonicalizer.canonicalize(prepare_mono(harmonic_tone(2 * TEST_FRAME_COUNT, frequency=440.0)))

    assert longer.conditioners.log_duration == pytest.approx(shorter.conditioners.log_duration + 1.0)


@pytest.mark.parametrize("case", CANONICALIZER_CASES, ids=lambda case: case.name)
def test_a_transposed_tone_lands_closer_than_unrelated_content(case: CanonicalizerCase) -> None:
    """Aligning the picture is what makes one instrument at two pitches read as one instrument."""
    canonicalizer = CANONICALIZER_REGISTRY[case.name](anchor=Anchor.FUNDAMENTAL)

    low = canonicalizer.canonicalize(prepare_mono(harmonic_tone(TEST_FRAME_COUNT, frequency=220.0)))
    high = canonicalizer.canonicalize(prepare_mono(harmonic_tone(TEST_FRAME_COUNT, frequency=440.0)))
    unrelated = canonicalizer.canonicalize(prepare_mono(noise_burst(TEST_FRAME_COUNT, seed=1)))

    transposed_distance = float(np.sqrt(np.mean((low.grid - high.grid) ** 2)))
    unrelated_distance = float(np.sqrt(np.mean((low.grid - unrelated.grid) ** 2)))
    assert transposed_distance < unrelated_distance


def test_the_log_frequency_axis_reads_prepared_frames_as_they_are() -> None:
    """The subsonic band leaves once, where audio comes in, so canonicalizing filters nothing further."""
    geometry = grid_geometry()
    mono = prepare_mono(harmonic_tone(TEST_FRAME_COUNT, frequency=55.0))
    bands = band_weights(geometry) @ np.abs(analysis_transform(mono, geometry=geometry))

    image = CANONICALIZER_REGISTRY["log_frequency"]().canonicalize(mono)

    np.testing.assert_allclose(image.grid, to_sound_image(bands, geometry=geometry, frame_count=mono.shape[0]).grid)


def test_the_band_weights_are_built_once_per_geometry_and_shared_read_only() -> None:
    geometry = grid_geometry()

    assert band_weights(geometry) is band_weights(geometry)
    with pytest.raises(ValueError, match="read-only"):
        band_weights(geometry)[0, 0] = 1.0
