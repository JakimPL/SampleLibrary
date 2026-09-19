from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray

from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.measurement.ladders.readings import (
    StepVerdict,
    profile_shift,
    read_ladder,
    read_pair,
    truth_discrimination_db,
)
from samplemorph.measurement.ladders.tables import is_central
from samplemorph.measurement.ladders.truth import Ladder, LadderRecipe, UnrelatedPair
from samplemorph.measurement.ladders.walkers import CrossfadeWalker, LatentWalker, TranslationOracle, Walk
from samplemorph.tones import HarmonicTone, harmonic_tone
from tests.samplemorph.measurement.ladders.conftest import AXIS, INTERVAL_SEMITONES, WEIGHTS

SHIFT_TOLERANCE_SEMITONES = 0.5
TRUTH_SHIFT_TOLERANCE_SEMITONES = 0.3


class _FlatteningAutoencoder:
    """A latent that is the grid itself laid flat, so its straight lines are the crossfade."""

    def __init__(self, shape: tuple[int, int]) -> None:
        self._shape = shape

    def encode(self, grids: NDArray[np.float32]) -> NDArray[np.float32]:
        return grids.reshape(grids.shape[0], -1)

    def decode(self, latents: NDArray[np.float32]) -> NDArray[np.float32]:
        return latents.reshape(latents.shape[0], *self._shape)


class _LoudnessCritic:
    """A critic that reads how loud a grid is on average, so every reading can be told from where it came."""

    def score(self, grids: NDArray[np.float32]) -> NDArray[np.float32]:
        loudness: NDArray[np.float32] = grids.mean(axis=(1, 2)).astype(np.float32)
        return loudness


def _flat_walker() -> LatentWalker:
    return LatentWalker(
        name="flat",
        autoencoder=_FlatteningAutoencoder((AXIS.band_count, AXIS.geometry.time_columns)),
        critic=_LoudnessCritic(),
    )


def _switched(ladder: Ladder) -> Walk:
    """A path that holds the first end until the middle and the second from there."""
    path = np.stack([ladder.truth[0] if weight < 0.5 else ladder.truth[-1] for weight in ladder.weights])
    return Walk(reconstructions=ladder.truth, path=path, critique=None)


def test_the_crossfade_reads_as_a_crossfade_at_every_step(retuned: Ladder) -> None:
    steps = read_ladder(retuned, CrossfadeWalker().walk(retuned), axis=AXIS)

    assert len(steps) == len(WEIGHTS) - 2
    assert all(step.verdict is StepVerdict.FADED and step.moved_share == 0.0 for step in steps)


def test_the_crossfade_s_middle_stands_at_one_end_of_the_interval_rather_than_between(retuned: Ladder) -> None:
    (middle,) = [
        step for step in read_ladder(retuned, CrossfadeWalker().walk(retuned), axis=AXIS) if step.weight == 0.5
    ]

    assert middle.shift is not None
    assert abs(middle.shift.deviation_semitones) >= INTERVAL_SEMITONES / 2.0 - SHIFT_TOLERANCE_SEMITONES


def test_a_band_shift_of_the_first_end_reads_as_a_move_in_the_middle_of_the_ladder(retuned: Ladder) -> None:
    walk = TranslationOracle(bands_per_semitone=AXIS.bands_per_semitone).walk(retuned)
    assert walk is not None

    central = [step for step in read_ladder(retuned, walk, axis=AXIS) if is_central(step.weight)]

    assert all(step.verdict is StepVerdict.MOVED for step in central)
    assert all(step.moved_share > 0.5 for step in central)
    assert all(
        step.shift is not None and abs(step.shift.deviation_semitones) < SHIFT_TOLERANCE_SEMITONES for step in central
    )


def test_a_path_that_holds_one_end_and_jumps_to_the_other_reads_as_a_switch(retuned: Ladder) -> None:
    central = [step for step in read_ladder(retuned, _switched(retuned), axis=AXIS) if is_central(step.weight)]

    assert all(step.verdict is StepVerdict.SWITCHED for step in central)


def test_the_truth_s_own_picture_moves_by_the_weight_s_share_of_the_interval(retuned: Ladder) -> None:
    bands = AXIS.reading_bands(interval_semitones=INTERVAL_SEMITONES)

    shifts = [
        profile_shift(step, retuned.truth[0], bands=bands, axis=AXIS, largest=INTERVAL_SEMITONES)
        for step in retuned.truth
    ]

    assert np.allclose(shifts, np.asarray(WEIGHTS) * INTERVAL_SEMITONES, atol=TRUTH_SHIFT_TOLERANCE_SEMITONES)


def test_the_oracle_walks_only_a_ladder_whose_truth_is_a_translation(recipe: LadderRecipe) -> None:
    pair = UnrelatedPair(name="pair", weights=WEIGHTS, ends=np.stack([np.zeros((113, 64), np.float32)] * 2))

    assert TranslationOracle(bands_per_semitone=1).walk_pair(pair) is None


def test_a_latent_that_is_the_grid_itself_walks_the_crossfade(retuned: Ladder) -> None:
    latent = _flat_walker().walk(retuned)
    crossfade = CrossfadeWalker().walk(retuned)

    assert np.allclose(latent.path, crossfade.path, atol=1e-6)
    assert np.array_equal(latent.reconstructions, crossfade.reconstructions)


def test_a_latent_walker_brings_its_critic_s_reading_of_the_true_step_the_crossfade_and_its_path(
    retuned: Ladder,
) -> None:
    steps = read_ladder(retuned, _flat_walker().walk(retuned), axis=AXIS)

    for index, step in enumerate(steps, start=1):
        assert step.critic is not None
        assert step.critic.sound == pytest.approx(float(retuned.truth[index].mean()), rel=1e-5)
        assert step.critic.path == pytest.approx(step.critic.crossfade, rel=1e-5)
    assert all(step.critic is None for step in read_ladder(retuned, CrossfadeWalker().walk(retuned), axis=AXIS))


def test_on_a_pair_the_critic_s_sound_is_its_reading_of_the_two_ends(recipe: LadderRecipe) -> None:
    ends = np.stack(
        [
            recipe.pooled(recipe.canonicalizer.canonicalize(prepare_mono(harmonic_tone(tone, rate_hz=44100.0))))
            for tone in (HarmonicTone(110.0, 900.0), HarmonicTone(330.0, 2500.0))
        ]
    )
    pair = UnrelatedPair(name="pair", weights=WEIGHTS, ends=ends)

    steps = read_pair(pair, _flat_walker().walk_pair(pair), axis=AXIS)

    sounds = [step.critic.sound for step in steps if step.critic is not None]
    assert sounds == pytest.approx([float(ends.mean())] * len(steps), rel=1e-5)


def test_a_crossfade_between_unrelated_samples_departs_from_nothing(recipe: LadderRecipe) -> None:
    ends = np.stack(
        [
            recipe.pooled(recipe.canonicalizer.canonicalize(prepare_mono(harmonic_tone(tone, rate_hz=44100.0))))
            for tone in (HarmonicTone(110.0, 900.0), HarmonicTone(330.0, 2500.0))
        ]
    )
    pair = UnrelatedPair(name="pair", weights=WEIGHTS, ends=ends)

    steps = read_pair(pair, CrossfadeWalker().walk_pair(pair), axis=AXIS)

    assert all(step.departure == pytest.approx(0.0, abs=1e-6) for step in steps)
    assert all(step.endpoint_distance_db > 0.0 for step in steps)


def test_a_ladder_whose_ends_agree_has_nothing_to_tell_apart(retuned: Ladder) -> None:
    still = Ladder(
        family=retuned.family,
        name="still",
        interval_semitones=INTERVAL_SEMITONES,
        weights=WEIGHTS,
        truth=np.repeat(retuned.truth[:1], len(WEIGHTS), axis=0),
    )

    assert truth_discrimination_db(still, axis=AXIS) == pytest.approx(0.0)
    assert truth_discrimination_db(retuned, axis=AXIS) > 0.0
