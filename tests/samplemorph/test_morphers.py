from __future__ import annotations

import numpy as np
import pytest

from samplemorph.codecs.identity import IdentityCodec
from samplemorph.geometry import log_frequency_geometry, mel_geometry
from samplemorph.images import Conditioners, SampleLatent
from samplemorph.measurement.plausibility import MorphEndpoint, morph_plausibility
from samplemorph.morphers import MorphWeights
from samplemorph.morphers.linear import LinearMorpher
from samplemorph.registries import CANONICALIZER_REGISTRY
from tests.samplemorph.conftest import TEST_FRAME_COUNT, harmonic_tone

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
    first = codec.encode(canonicalizer.canonicalize(harmonic_tone(TEST_FRAME_COUNT, frequency=220.0)))
    second = codec.encode(canonicalizer.canonicalize(harmonic_tone(TEST_FRAME_COUNT, frequency=660.0)))

    plausibility = morph_plausibility(
        MorphEndpoint(sample_hash=FIRST_HASH, latent=first),
        MorphEndpoint(sample_hash=SECOND_HASH, latent=second),
        codec=codec,
        morpher=LinearMorpher(),
    )

    assert plausibility.is_monotone
    assert plausibility.steps[0].distance_to_first == pytest.approx(0.0)
    assert plausibility.steps[-1].distance_to_second == pytest.approx(0.0)


def test_measuring_a_morph_path_asks_for_at_least_two_weights() -> None:
    canonicalizer = CANONICALIZER_REGISTRY["mel"]()
    codec = IdentityCodec(canonicalizer.geometry)
    latent = codec.encode(canonicalizer.canonicalize(harmonic_tone(TEST_FRAME_COUNT, frequency=220.0)))

    with pytest.raises(ValueError, match="at least two weights"):
        morph_plausibility(
            MorphEndpoint(sample_hash=FIRST_HASH, latent=latent),
            MorphEndpoint(sample_hash=SECOND_HASH, latent=latent),
            codec=codec,
            morpher=LinearMorpher(),
            weights=(0.5,),
        )
