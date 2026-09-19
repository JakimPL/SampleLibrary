from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from math import ceil, floor
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.canonicalizers.common import shift_bands
from samplemorph.measurement.comparison import grid_distance
from samplemorph.measurement.ladders.axis import PooledAxis
from samplemorph.measurement.ladders.truth import MIDDLE_WEIGHT, Ladder, UnrelatedPair
from samplemorph.measurement.ladders.walkers import Critique, Walk, crossfade
from samplemorph.measurement.plausibility import blend_distance, spectral_spread

MINIMUM_DISCRIMINATION_DB: Final[float] = 4.0
SHIFT_SEARCH_MARGIN_SEMITONES: Final[float] = 1.0


@unique
class StepVerdict(StrEnum):
    """Which reference a step of a path stands nearest: the truth, the crossfade, an end, or none of them.

    A step is placed by its nearest reference, and read as none of them when it stands further from
    every one than the truth stands from the crossfade, which is the distance a reading can tell
    things apart by at that step.
    """

    MOVED = "moved"
    FADED = "faded"
    SWITCHED = "switched"
    NEITHER = "neither"


@dataclass(frozen=True)
class ShiftReading:
    """How far a step's picture stands from the first end's along the band axis, beside how far the truth stands."""

    semitones: float
    expected_semitones: float

    @property
    def deviation_semitones(self) -> float:
        return self.semitones - self.expected_semitones


@dataclass(frozen=True)
class CriticReading:
    """What a model's own critic reads at one step: of a sound there, of the crossfade there, and of the path there.

    For a ladder the sound is the walker's reading of the true step; for a pair of unrelated
    samples, whose middle nobody knows, it is the walker's readings of the two ends, averaged.
    """

    sound: float
    crossfade: float
    path: float


@dataclass(frozen=True)
class StepReading:
    """One step of a path read against the ladder's truth, every distance a difference of shape in decibels over the trusted bands.

    `truth_distance_db` is how far the step stands from the walker's own reading of the true step,
    `crossfade_distance_db` from the crossfade of its readings of the two ends, and
    `end_distance_db` from the nearer of those two ends. `discrimination_db` is how far the truth
    stands from the crossfade there, and `reconstruction_db` how far the walker's reading of the
    true step stands from the truth itself. `spread_excess` is how much more widely the step's
    energy spreads across bands than the ends' spread at that weight, which two pictures laid over
    each other raise. `shift` is read on ladders whose truth is a translation, and `critic` for a
    walker that brings a critic of its own.
    """

    weight: float
    truth_distance_db: float
    crossfade_distance_db: float
    end_distance_db: float
    discrimination_db: float
    reconstruction_db: float
    spread_excess: float
    shift: ShiftReading | None
    critic: CriticReading | None

    @property
    def moved_share(self) -> float:
        """Where the step stands between the crossfade, at 0, and the truth, at 1."""
        return self.crossfade_distance_db / (self.truth_distance_db + self.crossfade_distance_db)

    @property
    def verdict(self) -> StepVerdict:
        nearest, verdict = min(
            (
                (self.truth_distance_db, StepVerdict.MOVED),
                (self.crossfade_distance_db, StepVerdict.FADED),
                (self.end_distance_db, StepVerdict.SWITCHED),
            ),
            key=lambda reference: reference[0],
        )
        return verdict if nearest <= self.discrimination_db else StepVerdict.NEITHER


@dataclass(frozen=True)
class PairStepReading:
    """One step of a path between two unrelated samples, read against their crossfade alone.

    `departure` is the step's distance from the crossfade over the distance between the two ends,
    so 0 is the crossfade and 1 as far from it as the ends are from each other. `critic` is read
    for a walker that brings a critic of its own.
    """

    weight: float
    departure: float
    end_distance_db: float
    endpoint_distance_db: float
    spread_excess: float
    critic: CriticReading | None


def truth_discrimination_db(ladder: Ladder, *, axis: PooledAxis) -> float:
    """How far a ladder's middle step stands from the crossfade of its ends, which is what any reading of it can tell apart.

    A band shift of a sound's picture stands about 3.4 dB from the same sound truly retuned by a
    whole number of bands, measured on a harmonic tone at one band per semitone, since the analysis
    window resolves the higher bands more finely than the lower ones. A ladder whose middle stands
    closer to the crossfade than `MINIMUM_DISCRIMINATION_DB` holds no move a reading can tell apart
    from that.
    """
    middle = int(np.argmin(np.abs(np.asarray(ladder.weights) - MIDDLE_WEIGHT)))
    bands = axis.reading_bands(interval_semitones=ladder.interval_semitones)
    crossfaded = crossfade(ladder.truth[0], ladder.truth[-1], weights=(ladder.weights[middle],))[0]
    return _distance_db(ladder.truth[middle][bands], crossfaded[bands], axis=axis)


def read_ladder(ladder: Ladder, walk: Walk, *, axis: PooledAxis) -> tuple[StepReading, ...]:
    """Every step between a ladder's ends, read against the walker's readings of the truth."""
    bands = axis.reading_bands(interval_semitones=ladder.interval_semitones)
    first, second = walk.reconstructions[0], walk.reconstructions[-1]
    crossfaded = crossfade(first, second, weights=ladder.weights)
    readings = []
    for index in range(1, len(ladder.weights) - 1):
        weight = ladder.weights[index]
        step = walk.path[index]
        readings.append(
            StepReading(
                weight=weight,
                truth_distance_db=_distance_db(step[bands], walk.reconstructions[index][bands], axis=axis),
                crossfade_distance_db=_distance_db(step[bands], crossfaded[index][bands], axis=axis),
                end_distance_db=min(
                    _distance_db(step[bands], first[bands], axis=axis),
                    _distance_db(step[bands], second[bands], axis=axis),
                ),
                discrimination_db=_distance_db(walk.reconstructions[index][bands], crossfaded[index][bands], axis=axis),
                reconstruction_db=_distance_db(
                    walk.reconstructions[index][bands], ladder.truth[index][bands], axis=axis
                ),
                spread_excess=_spread_excess(step[bands], first[bands], second[bands], weight=weight),
                shift=(
                    ShiftReading(
                        semitones=profile_shift(step, first, bands=bands, axis=axis, largest=ladder.interval_semitones),
                        expected_semitones=weight * ladder.interval_semitones,
                    )
                    if ladder.is_translation
                    else None
                ),
                critic=_ladder_critic(walk.critique, index=index),
            )
        )
    return tuple(readings)


def read_pair(pair: UnrelatedPair, walk: Walk, *, axis: PooledAxis) -> tuple[PairStepReading, ...]:
    """Every step between two unrelated samples, read against the crossfade of the walker's readings of them."""
    bands = axis.reading_bands(interval_semitones=0.0)
    first, second = (reconstruction[bands].astype(np.float64) for reconstruction in walk.reconstructions)
    endpoint_distance = grid_distance(first, second)
    readings = []
    for index in range(1, len(pair.weights) - 1):
        weight = pair.weights[index]
        step = walk.path[index][bands].astype(np.float64)
        readings.append(
            PairStepReading(
                weight=weight,
                departure=blend_distance(
                    step, first=first, second=second, weight=weight, endpoint_distance=endpoint_distance
                ),
                end_distance_db=axis.dynamic_range_db * min(grid_distance(step, first), grid_distance(step, second)),
                endpoint_distance_db=axis.dynamic_range_db * endpoint_distance,
                spread_excess=_spread_excess(step, first, second, weight=weight),
                critic=_pair_critic(walk.critique, index=index),
            )
        )
    return tuple(readings)


def _ladder_critic(critique: Critique | None, *, index: int) -> CriticReading | None:
    if critique is None:
        return None
    return CriticReading(
        sound=float(critique.sounds[index]),
        crossfade=float(critique.crossfade[index]),
        path=float(critique.path[index]),
    )


def _pair_critic(critique: Critique | None, *, index: int) -> CriticReading | None:
    if critique is None:
        return None
    return CriticReading(
        sound=float(critique.sounds.mean()),
        crossfade=float(critique.crossfade[index]),
        path=float(critique.path[index]),
    )


def pair_endpoint_distance_db(ends: NDArray[np.float32], *, axis: PooledAxis) -> float:
    """How far two samples' pictures stand from each other over the trusted bands."""
    bands = axis.reading_bands(interval_semitones=0.0)
    return _distance_db(ends[0][bands], ends[1][bands], axis=axis)


def profile_shift(
    grid: NDArray[np.float32],
    reference: NDArray[np.float32],
    *,
    bands: NDArray[np.bool_],
    axis: PooledAxis,
    largest: float,
) -> float:
    """How many semitones up the band axis a grid's picture stands from a reference's, read from their spectra over time.

    Both grids are averaged over time into a profile across bands, and the reference's profile is
    moved band by band until it correlates best with the grid's over the trusted bands; the peak
    is refined between bands by the parabola through its neighbors. The search runs only from a
    semitone below the reference to a semitone past `largest`, since a harmonic spectrum also
    correlates with itself an octave or a twelfth away, and a wider search would find those.
    """
    profile = grid.mean(axis=1).astype(np.float64)
    reference_profile = reference.mean(axis=1).astype(np.float64)[:, None]
    per_semitone = axis.bands_per_semitone
    shifts = np.arange(
        floor(-SHIFT_SEARCH_MARGIN_SEMITONES * per_semitone),
        ceil((largest + SHIFT_SEARCH_MARGIN_SEMITONES) * per_semitone) + 1,
    )
    scores = np.array(
        [_correlation(profile[bands], shift_bands(reference_profile, float(shift))[:, 0][bands]) for shift in shifts]
    )
    best = int(np.argmax(scores))
    return float(shifts[best] + _parabolic_offset(scores, best)) / per_semitone


def _correlation(first: NDArray[np.float64], second: NDArray[np.float64]) -> float:
    """Pearson's correlation of two profiles, read as the worst score when either holds no variation to correlate."""
    first_spread, second_spread = float(first.std()), float(second.std())
    if first_spread == 0.0 or second_spread == 0.0:
        return -1.0
    return float(np.mean((first - first.mean()) * (second - second.mean())) / (first_spread * second_spread))


def _parabolic_offset(scores: NDArray[np.float64], best: int) -> float:
    """Where the parabola through the best score and its two neighbors peaks, relative to the best one."""
    if best in (0, scores.size - 1):
        return 0.0
    below, at, above = scores[best - 1], scores[best], scores[best + 1]
    curvature = below - 2.0 * at + above
    if curvature >= 0.0:
        return 0.0
    return float(0.5 * (below - above) / curvature)


def _distance_db(first: NDArray[np.float32], second: NDArray[np.float32], *, axis: PooledAxis) -> float:
    """How far two grids' shapes stand apart, in decibels, once the level they differ by across every cell is set aside.

    Every grid is normalized to its own peak, and a retuning changes how the peak stands against
    the rest of the sound, so two readings of one sound at two rates can differ by several decibels
    over every band while their shapes agree. The common offset is taken out, and the root mean
    square of what is left is the distance.
    """
    difference = first.astype(np.float64) - second.astype(np.float64)
    return axis.dynamic_range_db * grid_distance(difference - difference.mean(), np.zeros_like(difference))


def _spread_excess(
    step: NDArray[np.floating], first: NDArray[np.floating], second: NDArray[np.floating], *, weight: float
) -> float:
    ends = (1.0 - weight) * spectral_spread(first.astype(np.float64)) + weight * spectral_spread(
        second.astype(np.float64)
    )
    return spectral_spread(step.astype(np.float64)) - ends
