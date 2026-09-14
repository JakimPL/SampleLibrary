from __future__ import annotations

import numpy as np
import pytest

from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.codecs.identity import IdentityCodec
from samplemorph.geometry import Anchor, Geometry, log_frequency_geometry, mel_geometry
from samplemorph.images import Conditioners, SampleLatent, SoundImage
from samplemorph.measurement.plausibility import (
    MorphEndpoint,
    blend_distance,
    grid_energy,
    heard_pitch_semitones,
    morph_plausibility,
    spectral_spread,
)
from samplemorph.morphers import MorphWeights
from samplemorph.morphers.linear import LinearMorpher
from samplemorph.registries import CANONICALIZER_REGISTRY
from tests.samplemorph.conftest import TEST_FRAME_COUNT, harmonic_tone, noise_burst

FIRST_HASH = "a" * 64
SECOND_HASH = "b" * 64


def _latent(values: list[float], *, translation: float, duration: float, gain: float) -> SampleLatent:
    return SampleLatent(
        values=np.array(values),
        conditioners=Conditioners(translation_semitones=translation, log_duration=duration, log_gain=gain),
        geometry=mel_geometry(),
    )


def test_a_morph_at_zero_returns_the_first_latent() -> None:
    first = _latent([1.0, 2.0], translation=0.0, duration=-1.0, gain=-2.0)
    second = _latent([5.0, 6.0], translation=12.0, duration=-3.0, gain=-4.0)

    morphed = LinearMorpher().morph(first, second, weights=MorphWeights.uniform(0.0))

    assert np.allclose(morphed.values, first.values)
    assert morphed.conditioners == first.conditioners


def test_a_morph_at_one_returns_the_second_latent() -> None:
    first = _latent([1.0, 2.0], translation=0.0, duration=-1.0, gain=-2.0)
    second = _latent([5.0, 6.0], translation=12.0, duration=-3.0, gain=-4.0)

    morphed = LinearMorpher().morph(first, second, weights=MorphWeights.uniform(1.0))

    assert np.allclose(morphed.values, second.values)
    assert morphed.conditioners == second.conditioners


def test_a_morph_halfway_lands_between_both_latents_and_both_conditioners() -> None:
    first = _latent([0.0, 0.0], translation=0.0, duration=-2.0, gain=-4.0)
    second = _latent([4.0, 8.0], translation=12.0, duration=-4.0, gain=-8.0)

    morphed = LinearMorpher().morph(first, second, weights=MorphWeights.uniform(0.5))

    assert np.allclose(morphed.values, [2.0, 4.0])
    assert morphed.conditioners.translation_semitones == pytest.approx(6.0)
    assert morphed.conditioners.log_duration == pytest.approx(-3.0)
    assert morphed.conditioners.log_gain == pytest.approx(-6.0)


def test_the_latent_and_the_conditioners_travel_under_their_own_weights() -> None:
    """Holding pitch while timbre moves is most of what makes a morph musical."""
    first = _latent([0.0], translation=0.0, duration=-2.0, gain=-4.0)
    second = _latent([10.0], translation=24.0, duration=-2.0, gain=-4.0)

    morphed = LinearMorpher().morph(first, second, weights=MorphWeights(latent=1.0, conditioners=0.0))

    assert np.allclose(morphed.values, [10.0])
    assert morphed.conditioners.translation_semitones == pytest.approx(0.0)


def test_a_morph_between_latents_of_different_sizes_says_so() -> None:
    first = _latent([1.0, 2.0], translation=0.0, duration=-1.0, gain=-1.0)
    second = _latent([1.0], translation=0.0, duration=-1.0, gain=-1.0)

    with pytest.raises(ValueError, match="latents of one size"):
        LinearMorpher().morph(first, second, weights=MorphWeights.uniform(0.5))


def test_a_morph_between_latents_on_different_axes_says_so() -> None:
    first = _latent([1.0, 2.0], translation=0.0, duration=-1.0, gain=-1.0)
    second = SampleLatent(
        values=np.array([1.0, 2.0]),
        conditioners=first.conditioners,
        geometry=log_frequency_geometry(),
    )

    with pytest.raises(ValueError, match="one geometry"):
        LinearMorpher().morph(first, second, weights=MorphWeights.uniform(0.5))


def test_a_weight_outside_the_unit_range_is_rejected() -> None:
    with pytest.raises(ValueError):
        MorphWeights.uniform(1.5)


def test_a_lossless_morph_travels_from_one_endpoint_to_the_other() -> None:
    """The standing guard: a path that leaves the first sample and reaches the second is a morph,
    and one that stays near both throughout is the crossfade this project already rejected.
    """
    canonicalizer = CANONICALIZER_REGISTRY["mel"]()
    codec = IdentityCodec(canonicalizer.geometry)
    first = codec.encode(canonicalizer.canonicalize(prepare_mono(harmonic_tone(TEST_FRAME_COUNT, frequency=220.0))))
    second = codec.encode(canonicalizer.canonicalize(prepare_mono(harmonic_tone(TEST_FRAME_COUNT, frequency=660.0))))

    plausibility = morph_plausibility(
        MorphEndpoint(sample_hash=FIRST_HASH, latent=first),
        MorphEndpoint(sample_hash=SECOND_HASH, latent=second),
        codec=codec,
        morpher=LinearMorpher(),
    )

    assert plausibility.is_monotone
    assert plausibility.steps[0].distance_to_first == pytest.approx(0.0)
    assert plausibility.steps[-1].distance_to_second == pytest.approx(0.0)


class SnappingCodec:
    """Decodes a grid by keeping only the cells above half, so a blend of two sounds comes back as neither.

    Its latent is the grid itself, like the identity codec's, which makes it the smallest codec
    whose decoding is more than the average of what it was handed.
    """

    def __init__(self, geometry: Geometry) -> None:
        self._geometry = geometry

    @property
    def latent_size(self) -> int:
        band_count, time_columns = self._geometry.grid_shape
        return band_count * time_columns

    def encode(self, image: SoundImage) -> SampleLatent:
        return SampleLatent(
            values=image.grid.reshape(-1).copy(), conditioners=image.conditioners, geometry=self._geometry
        )

    def decode(self, latent: SampleLatent) -> SoundImage:
        grid = np.where(latent.values.reshape(self._geometry.grid_shape) > 0.5, 1.0, 0.0)
        return SoundImage(grid=grid, conditioners=latent.conditioners, geometry=self._geometry)


def test_a_lossless_linear_morph_is_exactly_the_crossfade_of_its_endpoints() -> None:
    """The identity codec under a linear morpher is the crossfade this reading exists to catch."""
    canonicalizer = CANONICALIZER_REGISTRY["mel"]()
    codec = IdentityCodec(canonicalizer.geometry)
    first = codec.encode(canonicalizer.canonicalize(prepare_mono(harmonic_tone(TEST_FRAME_COUNT, frequency=220.0))))
    second = codec.encode(canonicalizer.canonicalize(prepare_mono(noise_burst(TEST_FRAME_COUNT, seed=1))))

    plausibility = morph_plausibility(
        MorphEndpoint(sample_hash=FIRST_HASH, latent=first),
        MorphEndpoint(sample_hash=SECOND_HASH, latent=second),
        codec=codec,
        morpher=LinearMorpher(),
    )

    assert plausibility.smallest_blend_distance == pytest.approx(0.0, abs=1e-9)
    assert all(step.blend_distance == pytest.approx(0.0, abs=1e-9) for step in plausibility.steps)


def test_a_codec_that_states_a_sound_of_its_own_reads_above_the_crossfade() -> None:
    canonicalizer = CANONICALIZER_REGISTRY["mel"]()
    codec = SnappingCodec(canonicalizer.geometry)
    first = codec.encode(canonicalizer.canonicalize(prepare_mono(harmonic_tone(TEST_FRAME_COUNT, frequency=220.0))))
    second = codec.encode(canonicalizer.canonicalize(prepare_mono(harmonic_tone(TEST_FRAME_COUNT, frequency=660.0))))

    plausibility = morph_plausibility(
        MorphEndpoint(sample_hash=FIRST_HASH, latent=first),
        MorphEndpoint(sample_hash=SECOND_HASH, latent=second),
        codec=codec,
        morpher=LinearMorpher(),
    )

    assert plausibility.smallest_blend_distance > 0.0
    assert plausibility.steps[0].blend_distance == pytest.approx(0.0, abs=1e-9)
    assert plausibility.steps[-1].blend_distance == pytest.approx(0.0, abs=1e-9)


def test_identical_endpoints_have_no_crossfade_to_be_told_from() -> None:
    grid = np.zeros((40, 4))
    grid[10] = 1.0

    assert blend_distance(grid, first=grid, second=grid, weight=0.5, endpoint_distance=0.0) == 0.0


SECOND_HARMONIC_LOUDEST = (0.3, 1.0, 0.5, 0.25)
PITCH_TOLERANCE_SEMITONES = 1.0
PITCH_SWING_SEMITONES = 3.0


def _pitch_path(anchor: Anchor) -> float:
    """The worst pitch deviation of a lossless morph between two notes an octave apart, one anchored on
    a loud second harmonic and the other on its fundamental."""
    canonicalizer = CANONICALIZER_REGISTRY["log_frequency"](anchor=anchor)
    codec = IdentityCodec(canonicalizer.geometry)
    first = codec.encode(
        canonicalizer.canonicalize(
            prepare_mono(harmonic_tone(TEST_FRAME_COUNT, frequency=220.0, weights=SECOND_HARMONIC_LOUDEST))
        )
    )
    second = codec.encode(canonicalizer.canonicalize(prepare_mono(harmonic_tone(TEST_FRAME_COUNT, frequency=440.0))))
    return morph_plausibility(
        MorphEndpoint(sample_hash=FIRST_HASH, latent=first),
        MorphEndpoint(sample_hash=SECOND_HASH, latent=second),
        codec=codec,
        morpher=LinearMorpher(),
    ).largest_pitch_deviation


def test_a_morph_anchored_on_the_fundamental_keeps_its_pitch_on_the_line_between_the_notes() -> None:
    assert _pitch_path(Anchor.FUNDAMENTAL) < PITCH_TOLERANCE_SEMITONES


def test_a_morph_anchored_on_the_loudest_band_swings_off_the_line_when_the_anchors_are_different_partials() -> None:
    """The finding behind the fundamental anchor, as a lossless path: an octave between the two
    anchors puts the midpoint's note off the line by half of it."""
    assert _pitch_path(Anchor.LOUDEST) > PITCH_SWING_SEMITONES


def test_the_heard_pitch_reads_the_note_an_image_was_made_from() -> None:
    canonicalizer = CANONICALIZER_REGISTRY["log_frequency"]()

    image = canonicalizer.canonicalize(prepare_mono(harmonic_tone(TEST_FRAME_COUNT, frequency=880.0)))

    assert heard_pitch_semitones(image) == pytest.approx(12.0, abs=PITCH_TOLERANCE_SEMITONES)


def test_measuring_a_morph_path_asks_for_at_least_two_weights() -> None:
    canonicalizer = CANONICALIZER_REGISTRY["mel"]()
    codec = IdentityCodec(canonicalizer.geometry)
    latent = codec.encode(canonicalizer.canonicalize(prepare_mono(harmonic_tone(TEST_FRAME_COUNT, frequency=220.0))))

    with pytest.raises(ValueError, match="at least two weights"):
        morph_plausibility(
            MorphEndpoint(sample_hash=FIRST_HASH, latent=latent),
            MorphEndpoint(sample_hash=SECOND_HASH, latent=latent),
            codec=codec,
            morpher=LinearMorpher(),
            weights=(0.5,),
        )


def test_a_straight_line_through_a_grid_of_decibels_thins_out_what_two_sounds_do_not_share() -> None:
    """The midpoint of a tone and a noise burst on a lossless grid keeps a fraction of either's energy."""
    canonicalizer = CANONICALIZER_REGISTRY["mel"]()
    codec = IdentityCodec(canonicalizer.geometry)
    first = codec.encode(canonicalizer.canonicalize(prepare_mono(harmonic_tone(TEST_FRAME_COUNT, frequency=220.0))))
    second = codec.encode(canonicalizer.canonicalize(prepare_mono(noise_burst(TEST_FRAME_COUNT, seed=1))))

    plausibility = morph_plausibility(
        MorphEndpoint(sample_hash=FIRST_HASH, latent=first),
        MorphEndpoint(sample_hash=SECOND_HASH, latent=second),
        codec=codec,
        morpher=LinearMorpher(),
    )

    assert plausibility.smallest_energy_share < 0.5
    assert plausibility.largest_spread_excess <= 0.0


def test_two_lines_at_once_spread_wider_and_carry_the_energy_of_both() -> None:
    one_line = np.zeros((40, 4))
    one_line[10] = 1.0
    other_line = np.zeros((40, 4))
    other_line[30] = 1.0
    both = np.maximum(one_line, other_line)

    assert spectral_spread(both) > max(spectral_spread(one_line), spectral_spread(other_line))
    assert grid_energy(both) == pytest.approx(grid_energy(one_line) + grid_energy(other_line))


def test_spectral_spread_reads_a_single_line_as_narrower_than_two() -> None:
    one_line = np.zeros((40, 4))
    one_line[10] = 1.0
    two_lines = one_line.copy()
    two_lines[30] = 1.0

    assert spectral_spread(one_line) == pytest.approx(0.0)
    assert spectral_spread(two_lines) == pytest.approx(np.log(2.0))
    assert spectral_spread(np.zeros((40, 4))) == pytest.approx(0.0)
