from __future__ import annotations

from samplemorph.measurement.pitch.reading import SyntheticReadings
from samplemorph.measurement.pitch.residuals import OCTAVE_JUMPS_SEMITONES
from samplemorph.measurement.pitch.synthetic import draw_family_tones
from samplemorph.measurement.pitch.tables import Stratum, reliability_rows, summary_rows
from samplemorph.measurement.pitch.trial_sets import family_trials, held_out_trials
from samplemorph.measurement.pitch.trials import TrialKind
from tests.samplemorph.measurement.pitch.conftest import REFEREES, VARIANTS, Reading, truthful_sample

READER = "under-test"
OCTAVE_OFF_FAMILY = "resonance-on-2"


def _family_readings(*, octave_off_family: str | None) -> tuple[tuple[Reading, ...], dict[str, SyntheticReadings]]:
    tones = draw_family_tones(count=2, random_seed=0)
    readings = {
        tone.name: SyntheticReadings(
            name=tone.name,
            readings={
                READER: Reading(
                    semitones=tone.truth_semitones
                    + (OCTAVE_JUMPS_SEMITONES[0] if tone.family.name == octave_off_family else 0.0),
                    reliability=0.9,
                )
            },
        )
        for tone in tones
    }
    return tones, readings


def test_a_reader_that_reads_the_truth_is_within_half_a_semitone_in_every_row() -> None:
    samples = tuple(
        truthful_sample(f"{index:064x}", stored_semitones=-12.0 + index, seconds=1.0 + index, sound_type="tonal")
        for index in range(6)
    )
    tones, readings = _family_readings(octave_off_family=None)
    trials = (
        *held_out_trials(samples, reader_names=REFEREES, variants=VARIANTS, referees=REFEREES),
        *family_trials(tones, readings, reader_names=(READER,)),
    )

    rows = summary_rows(trials)

    assert {row["stratum"] for row in rows} == {stratum.value for stratum in Stratum}
    assert all(row["within_share"] == 1.0 and row["read_share"] == 1.0 for row in rows)


def test_a_reader_an_octave_off_on_one_family_shows_it_on_that_family_alone() -> None:
    tones, readings = _family_readings(octave_off_family=OCTAVE_OFF_FAMILY)

    rows = summary_rows(family_trials(tones, readings, reader_names=(READER,)))

    groups = {row["value"]: row for row in rows if row["stratum"] == Stratum.GROUP.value}
    assert groups[OCTAVE_OFF_FAMILY]["octave_share"] == 1.0
    assert all(row["within_share"] == 1.0 for value, row in groups.items() if not value.startswith(OCTAVE_OFF_FAMILY))
    assert all(row["reading"] == TrialKind.FAMILY.value for row in rows)


def test_a_reliability_that_ranks_every_tone_over_every_noise_separates_them_fully() -> None:
    tones = {
        name: SyntheticReadings(name=name, readings={READER: Reading(semitones=0.0, reliability=0.9)})
        for name in ("tone-a", "tone-b")
    }
    noises = {
        "noise-a": SyntheticReadings(name="noise-a", readings={READER: Reading(semitones=0.0, reliability=0.1)}),
        "noise-b": SyntheticReadings(name="noise-b", readings={READER: None}),
    }

    rows = reliability_rows((), tones, noises, reader_names=(READER,))

    separated = next(row for row in rows if row["separation"] == "tones-against-noise")
    assert separated["area_under_curve"] == 1.0
