from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pytest

from samplecore.waveform import average_to_fraction_points
from sampledescriptor.canonicalizers import Canonicalizer
from sampledescriptor.canonicalizers.log_frequency import LogFrequencyCanonicalizer, band_weights, to_sound_image
from sampledescriptor.geometry import Anchor, grid_geometry
from sampledescriptor.registries import CANONICALIZER_REGISTRY
from samplemorph.canonicalizers.common import analysis_transform, prepare_mono
from samplemorph.geometry import log_frequency_geometry
from tests.samplemorph.conftest import TEST_FRAME_COUNT, harmonic_tone, noise_burst

GAIN_FACTOR = 0.25
GAIN_FACTOR_IN_OCTAVES = -2.0
RESAMPLING_INVARIANT_TOLERANCE_SEMITONES = 1.0
READING_ORDER_TOLERANCE = 1e-12


@dataclass(frozen=True)
class ReadingOrderCase:
    """A waveform length against the grid's 64 columns, read with or without moving the picture."""

    frames: int
    anchor: Anchor


READING_ORDER_CASES = tuple(
    ReadingOrderCase(frames=frames, anchor=anchor)
    # One analysis frame, fewer frames than columns, and many more.
    for frames in (100, 2048, 16 * TEST_FRAME_COUNT)
    for anchor in (Anchor.NONE, Anchor.FUNDAMENTAL)
)


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


@pytest.mark.parametrize("case", READING_ORDER_CASES, ids=lambda case: f"{case.frames}-frames-{case.anchor.value}")
def test_reading_time_before_frequency_draws_the_picture_bands_first_would(case: ReadingOrderCase) -> None:
    """The frames and the bins are both averaged, so the order they are read in leaves the picture as it is.

    The reference reads every frame onto the bands through the whole weight matrix, then the bands
    onto the time columns, from the prepared frames as they come in.
    """
    geometry = grid_geometry(anchor=case.anchor)
    mono = prepare_mono(harmonic_tone(case.frames, frequency=55.0))
    bands = band_weights(geometry).toarray() @ np.abs(analysis_transform(mono, geometry=geometry))
    columns = average_to_fraction_points(bands, point_count=geometry.time_columns, axis=1)
    reference = to_sound_image(columns, geometry=geometry, frame_count=mono.shape[0])

    image = LogFrequencyCanonicalizer(geometry).canonicalize(mono)

    np.testing.assert_allclose(image.grid, reference.grid, rtol=0.0, atol=READING_ORDER_TOLERANCE)
    assert image.conditioners.translation_semitones == reference.conditioners.translation_semitones
    assert image.conditioners.log_duration == reference.conditioners.log_duration
    assert image.conditioners.log_gain == pytest.approx(reference.conditioners.log_gain, abs=READING_ORDER_TOLERANCE)


def test_the_band_weights_are_built_once_per_geometry_and_shared_read_only() -> None:
    geometry = grid_geometry()

    assert band_weights(geometry) is band_weights(geometry)
    with pytest.raises(ValueError, match="read-only"):
        band_weights(geometry).data[0] = 1.0
