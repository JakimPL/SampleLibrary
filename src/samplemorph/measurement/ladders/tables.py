from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Final

import numpy as np

from samplecore.tables import TableValue
from samplemorph.measurement.ladders.readings import PairStepReading, StepReading, StepVerdict
from samplemorph.measurement.ladders.truth import Ladder, LadderFamily

CENTRAL_REACH: Final[float] = 0.125
WEIGHT_TOLERANCE: Final[float] = 1e-9
NOT_READ: Final[str] = ""
DECIMALS: Final[int] = 4


@dataclass(frozen=True)
class ReadLadder:
    """One walker's readings of one ladder, beside the ladder they were read on."""

    walker: str
    ladder: Ladder
    steps: tuple[StepReading, ...]


@dataclass(frozen=True)
class ReadPair:
    """One walker's readings of one pair of unrelated samples."""

    walker: str
    pair: str
    steps: tuple[PairStepReading, ...]


def is_central(weight: float) -> bool:
    """Whether a step lies close enough to the middle for a move and a switch to be told apart.

    Near either end a moved step, a switched one and a crossfaded one all stand within a fraction
    of a band of the end, so the summary reads the steps within `CENTRAL_REACH` of the middle.
    """
    return abs(weight - 0.5) <= CENTRAL_REACH + WEIGHT_TOLERANCE


def ladder_rows(read: ReadLadder) -> list[dict[str, TableValue]]:
    """One row per step of one walker's path up one ladder."""
    return [
        {
            "model": read.walker,
            "family": read.ladder.family.value,
            "ladder": read.ladder.name,
            "interval_semitones": read.ladder.interval_semitones,
            "weight": round(step.weight, DECIMALS),
            "truth_distance_db": round(step.truth_distance_db, DECIMALS),
            "crossfade_distance_db": round(step.crossfade_distance_db, DECIMALS),
            "end_distance_db": round(step.end_distance_db, DECIMALS),
            "discrimination_db": round(step.discrimination_db, DECIMALS),
            "reconstruction_db": round(step.reconstruction_db, DECIMALS),
            "moved_share": round(step.moved_share, DECIMALS),
            "verdict": step.verdict.value,
            "spread_excess": round(step.spread_excess, DECIMALS),
            "shift_semitones": NOT_READ if step.shift is None else round(step.shift.semitones, DECIMALS),
            "shift_deviation_semitones": (
                NOT_READ if step.shift is None else round(step.shift.deviation_semitones, DECIMALS)
            ),
        }
        for step in read.steps
    ]


def pair_rows(read: ReadPair) -> list[dict[str, TableValue]]:
    """One row per step of one walker's path between one pair of unrelated samples."""
    return [
        {
            "model": read.walker,
            "pair": read.pair,
            "weight": round(step.weight, DECIMALS),
            "departure": round(step.departure, DECIMALS),
            "end_distance_db": round(step.end_distance_db, DECIMALS),
            "endpoint_distance_db": round(step.endpoint_distance_db, DECIMALS),
            "spread_excess": round(step.spread_excess, DECIMALS),
        }
        for step in read.steps
    ]


def ladder_summary_rows(reads: tuple[ReadLadder, ...]) -> list[dict[str, TableValue]]:
    """The central steps of every walker's ladders, gathered per walker, family and interval."""
    groups: dict[tuple[str, LadderFamily, float], list[StepReading]] = defaultdict(list)
    ladder_counts: dict[tuple[str, LadderFamily, float], int] = defaultdict(int)
    for read in reads:
        key = (read.walker, read.ladder.family, read.ladder.interval_semitones)
        ladder_counts[key] += 1
        groups[key].extend(step for step in read.steps if is_central(step.weight))
    rows: list[dict[str, TableValue]] = []
    for key in sorted(groups, key=lambda group: (group[0], group[1].value, group[2])):
        walker, family, interval = key
        steps = groups[key]
        shifts = [abs(step.shift.deviation_semitones) for step in steps if step.shift is not None]
        rows.append(
            {
                "model": walker,
                "family": family.value,
                "interval_semitones": interval,
                "ladders": ladder_counts[key],
                "steps": len(steps),
                "moved_share": _median([step.moved_share for step in steps]),
                **{
                    f"verdict_{verdict.value}": round(
                        sum(step.verdict is verdict for step in steps) / max(len(steps), 1), DECIMALS
                    )
                    for verdict in StepVerdict
                },
                "shift_deviation_semitones": _median(shifts) if shifts else NOT_READ,
                "reconstruction_db": _median([step.reconstruction_db for step in steps]),
                "discrimination_db": _median([step.discrimination_db for step in steps]),
                "spread_excess": _median([step.spread_excess for step in steps]),
            }
        )
    return rows


def pair_summary_rows(reads: tuple[ReadPair, ...]) -> list[dict[str, TableValue]]:
    """The central steps of every walker's paths between unrelated samples, gathered per walker."""
    groups: dict[str, list[PairStepReading]] = defaultdict(list)
    pair_counts: dict[str, int] = defaultdict(int)
    for read in reads:
        pair_counts[read.walker] += 1
        groups[read.walker].extend(step for step in read.steps if is_central(step.weight))
    return [
        {
            "model": walker,
            "pairs": pair_counts[walker],
            "steps": len(steps),
            "departure": _median([step.departure for step in steps]),
            "end_distance_db": _median([step.end_distance_db for step in steps]),
            "spread_excess": _median([step.spread_excess for step in steps]),
        }
        for walker, steps in sorted(groups.items())
    ]


def _median(values: list[float]) -> float:
    return round(float(np.median(values)), DECIMALS) if values else float("nan")
