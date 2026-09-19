from __future__ import annotations

import pytest

from samplemorph.measurement.pitch.reading import STORED_VARIANT, SampleReadings
from samplemorph.measurement.pitch.trial_sets import UNSETTLED_REGISTER, held_out_trials, tercile_labels
from samplemorph.measurement.pitch.trials import TrialKind
from tests.samplemorph.measurement.pitch.conftest import (
    FIRST_REFEREE,
    REFEREES,
    SECOND_REFEREE,
    VARIANTS,
    Reading,
    truthful_sample,
)

A3_SEMITONES = -12.0


def test_a_reader_that_follows_every_variant_errs_nowhere() -> None:
    trials = held_out_trials(
        (truthful_sample("a" * 64, stored_semitones=A3_SEMITONES, seconds=1.0, sound_type="tonal"),),
        reader_names=REFEREES,
        variants=VARIANTS,
        referees=REFEREES,
    )

    assert {trial.kind for trial in trials} == {TrialKind.RETUNING, TrialKind.INVARIANCE, TrialKind.CONSENSUS}
    assert all(trial.error_semitones == pytest.approx(0.0) for trial in trials)
    assert all(trial.context is not None and trial.context.register == "C3" for trial in trials)


def test_a_sample_the_referees_place_apart_asks_no_consensus_and_stays_unsettled() -> None:
    sample = truthful_sample("b" * 64, stored_semitones=A3_SEMITONES, seconds=1.0, sound_type="tonal")
    disputed = SampleReadings(
        sample_hash=sample.sample_hash,
        seconds=sample.seconds,
        sound_type=sample.sound_type,
        readings={**sample.readings, (STORED_VARIANT, SECOND_REFEREE): Reading(semitones=0.0, reliability=0.9)},
    )

    trials = held_out_trials((disputed,), reader_names=(FIRST_REFEREE,), variants=VARIANTS, referees=REFEREES)

    assert TrialKind.CONSENSUS not in {trial.kind for trial in trials}
    assert all(trial.context is not None and trial.context.register == UNSETTLED_REGISTER for trial in trials)


def test_a_variant_a_reader_found_no_pitch_in_is_a_trial_with_no_reading() -> None:
    sample = truthful_sample("c" * 64, stored_semitones=A3_SEMITONES, seconds=1.0, sound_type="tonal")
    unread = SampleReadings(
        sample_hash=sample.sample_hash,
        seconds=sample.seconds,
        sound_type=sample.sound_type,
        readings={**sample.readings, (VARIANTS[0].name, FIRST_REFEREE): None},
    )

    trials = held_out_trials((unread,), reader_names=(FIRST_REFEREE,), variants=VARIANTS, referees=REFEREES)

    missing = next(trial for trial in trials if trial.group == VARIANTS[0].name)
    assert missing.found_semitones is None and missing.reliability == 0.0


def test_terciles_name_each_value_by_its_third_with_ties_on_a_cut_falling_below_it() -> None:
    assert tercile_labels([0.0, 0.0, 0.0, 0.5, 0.9, 1.0], labels=("low", "middle", "high")) == (
        "low",
        "low",
        "low",
        "middle",
        "high",
        "high",
    )
