from __future__ import annotations

import numpy as np
import pytest
from trackmod.core.samples.depth import BitDepth

from samplemorph.canonicalizers.common import PreparedMono, prepare_mono
from samplemorph.measurement.pitch.changes import (
    LevelChange,
    Requantization,
    Retuning,
    TimeStretch,
    default_changes,
)
from samplemorph.measurement.pitch.trials import TrialKind
from samplemorph.tones import HarmonicTone, harmonic_tone

RATE_HZ = 44100.0
HOP_TOLERANCE_FRAMES = 512


@pytest.fixture(scope="module")
def tone() -> PreparedMono:
    return prepare_mono(harmonic_tone(HarmonicTone(fundamental_hz=220.0, resonance_hz=1500.0), rate_hz=RATE_HZ))


def test_a_retuning_shortens_the_sound_by_the_ratio_it_raises_it(tone: PreparedMono) -> None:
    retuned = Retuning(semitones=12.0)(tone)

    assert len(retuned) == pytest.approx(len(tone) / 2, abs=1)


@pytest.mark.parametrize("factor", [0.5, 2.0])
def test_a_stretch_makes_the_sound_its_factor_as_long(tone: PreparedMono, factor: float) -> None:
    stretched = TimeStretch(duration_factor=factor)(tone)

    assert abs(len(stretched) - factor * len(tone)) <= HOP_TOLERANCE_FRAMES


def test_a_level_change_scales_the_waveform(tone: PreparedMono) -> None:
    quieter = LevelChange(decibels=-20.0)(tone)

    assert np.allclose(quieter, tone / 10.0)


def test_a_requantized_sound_lies_on_the_eight_bit_grid(tone: PreparedMono) -> None:
    requantized = Requantization(depth=BitDepth.EIGHT)(tone)

    steps = requantized * 128.0
    assert np.allclose(steps, np.round(steps))
    assert np.abs(requantized - tone).max() <= 1.0 / 256.0 + 1e-12


def test_every_default_change_has_its_own_name_and_a_retuning_expects_its_own_interval() -> None:
    changes = default_changes()

    assert len({change.name for change in changes}) == len(changes)
    for change in changes:
        match change:
            case Retuning():
                assert change.kind is TrialKind.RETUNING
                assert change.expected_semitones == change.semitones
            case _:
                assert change.kind is TrialKind.INVARIANCE
                assert change.expected_semitones == 0.0
