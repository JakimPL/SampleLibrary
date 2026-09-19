from __future__ import annotations

import numpy as np
import pytest

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.geometry import SEMITONES_PER_OCTAVE
from samplemorph.measurement.pitch.synthetic import (
    HIGHEST_FUNDAMENTAL_HZ,
    LOWEST_FUNDAMENTAL_HZ,
    NOISE_EXPONENTS,
    TONE_FAMILIES,
    TRACKER_RATE_HZ,
    Rendering,
    draw_family_tones,
    draw_noise_bursts,
    draw_tone_pairs,
)

TONE_COUNT = 3
PAIR_COUNT = 20
TOLERANCE_HZ = 1e-6


def test_every_family_is_drawn_both_ways_at_one_set_of_fundamentals() -> None:
    tones = draw_family_tones(count=TONE_COUNT, random_seed=0)

    assert len(tones) == len(TONE_FAMILIES) * len(Rendering) * TONE_COUNT
    assert len({tone.name for tone in tones}) == len(tones)
    fundamentals = {
        tuple(sorted(tone.tone.fundamental_hz for tone in tones if tone.family is family)) for family in TONE_FAMILIES
    }
    assert len(fundamentals) == 1


def test_an_eight_bit_tone_sounds_higher_in_the_nominal_frame_by_the_interval_between_the_rates() -> None:
    tones = draw_family_tones(count=1, random_seed=0)
    clean = next(tone for tone in tones if tone.rendering is Rendering.CLEAN)
    eight_bit = next(tone for tone in tones if tone.rendering is Rendering.EIGHT_BIT and tone.family is clean.family)

    assert eight_bit.truth_semitones - clean.truth_semitones == pytest.approx(
        SEMITONES_PER_OCTAVE * np.log2(NOMINAL_WAV_RATE / TRACKER_RATE_HZ)
    )
    assert eight_bit.group != clean.group


def test_a_pair_joins_two_families_at_its_interval_within_the_register() -> None:
    for pair in draw_tone_pairs(count=PAIR_COUNT, random_seed=0):
        first, second = pair.first.tone.fundamental_hz, pair.second.tone.fundamental_hz

        assert pair.first.family != pair.second.family
        assert SEMITONES_PER_OCTAVE * np.log2(second / first) == pytest.approx(pair.interval_semitones)
        assert LOWEST_FUNDAMENTAL_HZ - TOLERANCE_HZ <= min(first, second)
        assert max(first, second) <= HIGHEST_FUNDAMENTAL_HZ + TOLERANCE_HZ


def test_noise_bursts_take_the_colors_in_turn_each_on_its_own_seed() -> None:
    noises = draw_noise_bursts(count=2 * len(NOISE_EXPONENTS), random_seed=0)

    assert tuple(noise.exponent for noise in noises) == 2 * NOISE_EXPONENTS
    assert len({noise.random_seed for noise in noises}) == len(noises)
    assert not np.allclose(noises[0].render(), noises[len(NOISE_EXPONENTS)].render())
