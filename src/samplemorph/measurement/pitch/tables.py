from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from enum import StrEnum, unique
from typing import Final

import numpy as np
from scipy.stats import rankdata

from samplecore.auditory.sound_type import SoundType
from samplecore.tables import TableValue
from samplemorph.measurement.pitch.reader import ReadPitch
from samplemorph.measurement.pitch.reading import STORED_VARIANT, SampleReadings, SyntheticReadings
from samplemorph.measurement.pitch.residuals import Residual, residual_of
from samplemorph.measurement.pitch.trial_sets import tercile_labels
from samplemorph.measurement.pitch.trials import SampleContext, Trial, TrialKind

DECIMALS: Final[int] = 4
NOT_READ: Final[str] = ""
ALL_TRIALS: Final[str] = "all"
RELIABILITY_TERCILES: Final[tuple[str, str, str]] = ("low", "middle", "high")
TONES_AGAINST_NOISE: Final[str] = "tones-against-noise"
TONAL_AGAINST_NOISE: Final[str] = "tonal-against-noise"


@unique
class Stratum(StrEnum):
    """How a reader's trials of one kind are split in the summary.

    `ALL` keeps them together, `GROUP` splits them by what they ask (the retuning, the change, the
    family or the interval), `RELIABILITY` by the tercile of the reader's own trust, and the last
    three by the held-out sample's sound type, duration tercile and settled octave.
    """

    ALL = "all"
    GROUP = "group"
    RELIABILITY = "reliability"
    SOUND_TYPE = "sound-type"
    DURATION = "duration"
    REGISTER = "register"


def trial_rows(trials: tuple[Trial, ...]) -> list[dict[str, TableValue]]:
    """One row per trial: what it asked, what the reader found, and where its sample falls."""
    return [
        {
            "reader": trial.reader,
            "reading": trial.kind.value,
            "group": trial.group,
            "source": trial.source,
            "expected_semitones": round(trial.expected_semitones, DECIMALS),
            "found_semitones": _rounded(trial.found_semitones),
            "error_semitones": _rounded(trial.error_semitones),
            "residual": NOT_READ if trial.residual is None else trial.residual.value,
            "reliability": round(trial.reliability, DECIMALS),
            "sound_type": NOT_READ if trial.context is None else trial.context.sound_type,
            "duration": NOT_READ if trial.context is None else trial.context.duration,
            "register": NOT_READ if trial.context is None else trial.context.register,
        }
        for trial in trials
    ]


def summary_rows(trials: tuple[Trial, ...]) -> list[dict[str, TableValue]]:
    """Every reader's trials of each kind, whole and split by every stratum that applies to them.

    A row counts the trials, the share the reader made a reading for, and among those made the
    median absolute error, the share within half a semitone, the shares an octave or a fifth off,
    and the median reliability.
    """
    by_reading: dict[tuple[str, TrialKind], list[Trial]] = defaultdict(list)
    for trial in trials:
        by_reading[(trial.reader, trial.kind)].append(trial)
    rows: list[dict[str, TableValue]] = []
    for (reader, kind), reading_trials in by_reading.items():
        for stratum in Stratum:
            for value, stratum_trials in _split(reading_trials, stratum=stratum).items():
                named: dict[str, TableValue] = {
                    "reader": reader,
                    "reading": kind.value,
                    "stratum": stratum.value,
                    "value": value,
                }
                rows.append(named | _summarized(stratum_trials))
    return rows


def reliability_rows(
    held_out: tuple[SampleReadings, ...],
    tones: Mapping[str, SyntheticReadings],
    noises: Mapping[str, SyntheticReadings],
    *,
    reader_names: tuple[str, ...],
) -> list[dict[str, TableValue]]:
    """How well each reader's reliability tells sounds with a pitch from sounds without one.

    Two separations are read as the area under the curve, the chance a pitched sound outranks an
    unpitched one: the clean synthetic tones against the noise bursts, and the held-out samples read
    as tonal against those read as noise. A sound a reader found no pitch in ranks at 0.
    """
    rows: list[dict[str, TableValue]] = []
    for name in reader_names:
        separations = {
            TONES_AGAINST_NOISE: (
                [_trust(readings.readings[name]) for readings in tones.values()],
                [_trust(readings.readings[name]) for readings in noises.values()],
            ),
            TONAL_AGAINST_NOISE: (
                _stored_trust(held_out, reader=name, sound_type=SoundType.TONAL),
                _stored_trust(held_out, reader=name, sound_type=SoundType.NOISE),
            ),
        }
        rows.extend(
            {
                "reader": name,
                "separation": separation,
                "pitched": len(pitched),
                "unpitched": len(unpitched),
                "area_under_curve": _area_under_curve(pitched, unpitched),
            }
            for separation, (pitched, unpitched) in separations.items()
        )
    return rows


def _split(trials: list[Trial], *, stratum: Stratum) -> dict[str, list[Trial]]:
    """The trials gathered by their value in one stratum, terciles lowest first and the rest in the order met.

    A synthetic trial has no sample to place, so the three sample strata gather held-out trials alone.
    """
    match stratum:
        case Stratum.ALL:
            return {ALL_TRIALS: trials}
        case Stratum.GROUP:
            return _gathered(trials, value_of=lambda trial: trial.group)
        case Stratum.RELIABILITY:
            return _by_reliability(trials)
        case Stratum.SOUND_TYPE:
            return _gathered_by_context(trials, value_of=lambda context: context.sound_type)
        case Stratum.DURATION:
            return _gathered_by_context(trials, value_of=lambda context: context.duration)
        case Stratum.REGISTER:
            return _gathered_by_context(trials, value_of=lambda context: context.register)


def _gathered(trials: list[Trial], *, value_of: Callable[[Trial], str]) -> dict[str, list[Trial]]:
    groups: dict[str, list[Trial]] = defaultdict(list)
    for trial in trials:
        groups[value_of(trial)].append(trial)
    return dict(groups)


def _gathered_by_context(trials: list[Trial], *, value_of: Callable[[SampleContext], str]) -> dict[str, list[Trial]]:
    groups: dict[str, list[Trial]] = defaultdict(list)
    for trial in trials:
        if trial.context is not None:
            groups[value_of(trial.context)].append(trial)
    return dict(groups)


def _by_reliability(trials: list[Trial]) -> dict[str, list[Trial]]:
    labels = tercile_labels([trial.reliability for trial in trials], labels=RELIABILITY_TERCILES)
    return {
        tercile: [trial for trial, label in zip(trials, labels, strict=True) if label == tercile]
        for tercile in RELIABILITY_TERCILES
        if tercile in labels
    }


def _summarized(trials: list[Trial]) -> dict[str, TableValue]:
    errors = [error for trial in trials if (error := trial.error_semitones) is not None]
    residuals = [residual_of(error) for error in errors]
    return {
        "trials": len(trials),
        "read_share": round(len(errors) / len(trials), DECIMALS),
        "median_absolute_error": _median([abs(error) for error in errors]),
        "within_share": _share(residuals, Residual.WITHIN),
        "octave_share": _share(residuals, Residual.OCTAVE),
        "fifth_share": _share(residuals, Residual.FIFTH),
        "median_reliability": _median([trial.reliability for trial in trials if trial.error_semitones is not None]),
    }


def _share(residuals: list[Residual], residual: Residual) -> float:
    return (
        round(sum(found is residual for found in residuals) / len(residuals), DECIMALS) if residuals else float("nan")
    )


def _stored_trust(held_out: tuple[SampleReadings, ...], *, reader: str, sound_type: SoundType) -> list[float]:
    return [
        _trust(sample.readings[(STORED_VARIANT, reader)])
        for sample in held_out
        if sample.sound_type == sound_type.value
    ]


def _trust(reading: ReadPitch | None) -> float:
    return 0.0 if reading is None else reading.reliability


def _area_under_curve(pitched: list[float], unpitched: list[float]) -> float:
    """The chance a pitched sound's score outranks an unpitched one's, ties counting half: the Mann-Whitney statistic scaled to ``[0, 1]``."""
    if not pitched or not unpitched:
        return float("nan")
    ranks = rankdata(np.asarray(pitched + unpitched, dtype=np.float64))
    pitched_rank_sum = float(ranks[: len(pitched)].sum())
    return round(
        (pitched_rank_sum - len(pitched) * (len(pitched) + 1) / 2.0) / (len(pitched) * len(unpitched)), DECIMALS
    )


def _median(values: list[float]) -> float:
    return round(float(np.median(values)), DECIMALS) if values else float("nan")


def _rounded(value: float | None) -> TableValue:
    return NOT_READ if value is None else round(value, DECIMALS)
