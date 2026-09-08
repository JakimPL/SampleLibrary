from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

from samplecore.waveform import resample_by_semitones
from samplemorph.canonicalizers import Canonicalizer
from samplemorph.measurement.comparison import grid_distance
from samplemorph.measurement.corpus import ProbeSample, unrelated_pairs

DEFAULT_SEMITONE_OFFSETS: Final[tuple[float, ...]] = (-17.0, -12.0, -7.0, -3.0, 3.0, 7.0, 12.0, 17.0)
DEFAULT_UNRELATED_PAIR_COUNT: Final[int] = 300


@dataclass(frozen=True)
class EquivarianceTrial:
    """One sample read at one retuning, against the same sample read as it is stored."""

    sample_hash: str
    semitone_offset: float
    grid_distance: float
    translation_error_semitones: float


@dataclass(frozen=True)
class OffsetSummary:
    """What a whole probe reported at one retuning."""

    semitone_offset: float
    trial_count: int
    median_grid_distance: float
    median_translation_error_semitones: float
    exact_translation_share: float


@dataclass(frozen=True)
class EquivarianceSummary:
    """What one canonicalizer's grid does when the same waveform is read at a different rate.

    `unrelated_grid_distance` is the yardstick: a grid whose distance under retuning stays far
    below it describes one sound at two pitches, and a grid whose distance approaches it describes
    two sounds. `explained_share` states that comparison as the fraction of the unrelated distance
    the canonicalizer removes.
    """

    canonicalizer_name: str
    unrelated_grid_distance: float
    offsets: tuple[OffsetSummary, ...]

    @property
    def median_grid_distance(self) -> float:
        return float(np.median([offset.median_grid_distance for offset in self.offsets]))

    @property
    def explained_share(self) -> float:
        return 1.0 - self.median_grid_distance / self.unrelated_grid_distance

    @property
    def median_translation_error_semitones(self) -> float:
        return float(np.median([offset.median_translation_error_semitones for offset in self.offsets]))


def equivariance_trials(
    probes: tuple[ProbeSample, ...],
    canonicalizer: Canonicalizer,
    *,
    semitone_offsets: tuple[float, ...] = DEFAULT_SEMITONE_OFFSETS,
) -> tuple[EquivarianceTrial, ...]:
    """Canonicalize each probe as stored and as retuned, and report how far the two grids sit apart.

    A logarithmic frequency axis turns retuning into a translation, and canonicalization moves that
    translation into the conditioners, so a grid that holds this property returns the same picture
    for both readings and two conditioners differing by the retuning applied.
    """
    trials = []
    for probe in probes:
        reference = canonicalizer.canonicalize(probe.mono)
        for semitone_offset in semitone_offsets:
            retuned = canonicalizer.canonicalize(resample_by_semitones(probe.mono, semitones=semitone_offset))
            reported = retuned.conditioners.translation_semitones - reference.conditioners.translation_semitones
            trials.append(
                EquivarianceTrial(
                    sample_hash=probe.sample.hash,
                    semitone_offset=semitone_offset,
                    grid_distance=grid_distance(reference.grid, retuned.grid),
                    translation_error_semitones=abs(reported - semitone_offset),
                )
            )
    return tuple(trials)


def unrelated_grid_distance(
    probes: tuple[ProbeSample, ...],
    canonicalizer: Canonicalizer,
    *,
    pair_count: int = DEFAULT_UNRELATED_PAIR_COUNT,
    random_seed: int,
) -> float:
    """The median grid distance between samples drawn independently of one another."""
    grids = [canonicalizer.canonicalize(probe.mono).grid for probe in probes]
    pairs = unrelated_pairs(len(grids), pair_count=pair_count, random_seed=random_seed)
    return float(np.median([grid_distance(grids[first], grids[second]) for first, second in pairs]))


def summarize_equivariance(
    trials: tuple[EquivarianceTrial, ...], *, canonicalizer_name: str, unrelated_distance: float
) -> EquivarianceSummary:
    """Gather trials into one report per retuning, plus the whole probe's headline comparison.

    Raises:
        ValueError: the trials are empty, leaving nothing to summarize.
    """
    if not trials:
        raise ValueError("equivariance trials are empty, so there is nothing to summarize")

    offsets = []
    for semitone_offset in sorted({trial.semitone_offset for trial in trials}):
        at_offset = [trial for trial in trials if trial.semitone_offset == semitone_offset]
        translation_errors = [trial.translation_error_semitones for trial in at_offset]
        offsets.append(
            OffsetSummary(
                semitone_offset=semitone_offset,
                trial_count=len(at_offset),
                median_grid_distance=float(np.median([trial.grid_distance for trial in at_offset])),
                median_translation_error_semitones=float(np.median(translation_errors)),
                exact_translation_share=float(np.mean([error < 0.5 for error in translation_errors])),
            )
        )
    return EquivarianceSummary(
        canonicalizer_name=canonicalizer_name,
        unrelated_grid_distance=unrelated_distance,
        offsets=tuple(offsets),
    )
