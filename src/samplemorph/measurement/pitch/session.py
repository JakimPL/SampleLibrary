from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from samplecore.tables import write_table
from samplemorph.measurement.pitch.pictures import draw_residuals
from samplemorph.measurement.pitch.reading import SampleReadings, SyntheticReadings, SyntheticSound, Variant
from samplemorph.measurement.pitch.synthetic import NoiseBurst, RenderedTone, Rendering, TonePair
from samplemorph.measurement.pitch.tables import reliability_rows, summary_rows, trial_rows
from samplemorph.measurement.pitch.trial_sets import family_trials, held_out_trials, pair_trials

READINGS_FILE_NAME: Final[str] = "readings.csv"
SUMMARY_FILE_NAME: Final[str] = "summary.csv"
RELIABILITY_FILE_NAME: Final[str] = "reliability.csv"
PICTURES_DIRECTORY_NAME: Final[str] = "pictures"
PICTURE_SUFFIX: Final[str] = ".png"


@dataclass(frozen=True)
class SyntheticSet:
    """The synthetic sounds one reading reads: the family tones, the pairs of tones, and the noise bursts."""

    tones: tuple[RenderedTone, ...]
    pairs: tuple[TonePair, ...]
    noises: tuple[NoiseBurst, ...]

    @property
    def sounds(self) -> tuple[SyntheticSound, ...]:
        """Every sound to render and read once: the tones, both tones of every pair, and the noises."""
        return (
            *self.tones,
            *(tone for pair in self.pairs for tone in (pair.first, pair.second)),
            *self.noises,
        )


@dataclass(frozen=True)
class PitchReadings:
    """Every reading one run made, by the readers named: each held-out sample's, and each synthetic sound's by its name."""

    reader_names: tuple[str, ...]
    held_out: tuple[SampleReadings, ...]
    synthetic: SyntheticSet
    synthetic_readings: Mapping[str, SyntheticReadings]


@dataclass(frozen=True)
class PitchReadingSummary:
    """What one reading wrote: how many trials it posed, and where."""

    trial_count: int
    output_directory: Path


def write_pitch_readings(
    readings: PitchReadings, *, variants: tuple[Variant, ...], referees: tuple[str, str], output_directory: Path
) -> PitchReadingSummary:
    """Pose every trial the readings answer, and write the tables and one picture of errors per reader.

    `readings.csv` holds one row per trial, `summary.csv` every reader's trials of each kind whole and
    split by stratum, and `reliability.csv` how well each reader's reliability tells pitched sounds
    from unpitched ones.
    """
    reader_names, synthetic = readings.reader_names, readings.synthetic
    trials = (
        *held_out_trials(readings.held_out, reader_names=reader_names, variants=variants, referees=referees),
        *family_trials(synthetic.tones, readings.synthetic_readings, reader_names=reader_names),
        *pair_trials(synthetic.pairs, readings.synthetic_readings, reader_names=reader_names),
    )
    clean_tones = {
        tone.name: readings.synthetic_readings[tone.name]
        for tone in synthetic.tones
        if tone.rendering is Rendering.CLEAN
    }
    noises = {noise.name: readings.synthetic_readings[noise.name] for noise in synthetic.noises}
    write_table(output_directory / READINGS_FILE_NAME, trial_rows(trials))
    write_table(output_directory / SUMMARY_FILE_NAME, summary_rows(trials))
    write_table(
        output_directory / RELIABILITY_FILE_NAME,
        reliability_rows(readings.held_out, clean_tones, noises, reader_names=reader_names),
    )
    for name in reader_names:
        draw_residuals(
            output_directory / PICTURES_DIRECTORY_NAME / f"{name}{PICTURE_SUFFIX}",
            tuple(trial for trial in trials if trial.reader == name),
            reader=name,
        )
    return PitchReadingSummary(trial_count=len(trials), output_directory=output_directory)
