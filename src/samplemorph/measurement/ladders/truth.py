from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.canonicalizers import Canonicalizer
from samplemorph.canonicalizers.common import PreparedMono, prepare_mono
from samplemorph.descriptors.pooling import pool_bands
from samplemorph.descriptors.views import retuned_view
from samplemorph.geometry import SEMITONES_PER_OCTAVE
from samplemorph.images import SoundImage
from samplemorph.measurement.ladders.axis import PooledAxis
from samplemorph.measurement.ladders.tones import ResonantTone, resonant_tone

MIDDLE_WEIGHT: Final[float] = 0.5
LOWEST_FUNDAMENTAL_HZ: Final[float] = 80.0
HIGHEST_FUNDAMENTAL_HZ: Final[float] = 320.0
LOWEST_RESONANCE_HZ: Final[float] = 800.0
HIGHEST_RESONANCE_HZ: Final[float] = 3200.0


@unique
class LadderFamily(StrEnum):
    """What moves along a ladder.

    `RETUNED` is a library sample read at rates spanning the interval, which moves every feature
    the sound has together, a translation of its whole picture. `PITCH` moves a synthetic tone's
    partials under a resonance that stays, `RESONANCE` moves the resonance over partials that stay,
    and `CONTRARY` moves the partials up and the resonance down at once, which no translation
    gives. `UNRELATED` pairs two library samples whose middle nobody knows.
    """

    RETUNED = "retuned"
    PITCH = "pitch"
    RESONANCE = "resonance"
    CONTRARY = "contrary"
    UNRELATED = "unrelated"


SYNTHETIC_FAMILIES: Final[tuple[LadderFamily, ...]] = (
    LadderFamily.PITCH,
    LadderFamily.RESONANCE,
    LadderFamily.CONTRARY,
)


@dataclass(frozen=True)
class Ladder:
    """A path between two sounds whose every step is known: the grid each weight should decode to.

    Shape: `truth` is ``(steps, bands, columns)``, one pooled grid per weight, the first and the
    last being the two ends. `interval_semitones` is how far the moving feature travels from end to
    end.
    """

    family: LadderFamily
    name: str
    interval_semitones: float
    weights: tuple[float, ...]
    truth: NDArray[np.float32]

    @property
    def is_translation(self) -> bool:
        """Whether the truth is the first end moved along the band axis, which a retuning is and a synthetic motion is not."""
        return self.family is LadderFamily.RETUNED


@dataclass(frozen=True)
class UnrelatedPair:
    """Two library samples whose middle nobody knows, read at `weights` for how far a path between them strays from their crossfade.

    Shape: `ends` is ``(2, bands, columns)``.
    """

    name: str
    weights: tuple[float, ...]
    ends: NDArray[np.float32]


@dataclass(frozen=True)
class SyntheticEnds:
    """The two tones a synthetic ladder runs between, and the interval its moving feature covers."""

    family: LadderFamily
    name: str
    interval_semitones: float
    first: ResonantTone
    second: ResonantTone


@dataclass(frozen=True)
class LadderRecipe:
    """How a ladder's grids are made: the canonicalizer and the pooling of the grid cache the models read."""

    canonicalizer: Canonicalizer
    axis: PooledAxis

    def pooled(self, image: SoundImage) -> NDArray[np.float32]:
        return pool_bands(image.grid, band_count=self.axis.band_count)


def ladder_weights(step_count: int) -> tuple[float, ...]:
    """`step_count` weights evenly from the first end to the second, both ends included.

    Raises:
        ValueError: fewer than three steps leave no step between the ends to read.
    """
    if step_count < 3:
        raise ValueError(f"a ladder needs at least one step between its ends, so three steps or more, got {step_count}")
    return tuple(float(weight) for weight in np.linspace(0.0, 1.0, step_count))


def retuned_ladder(
    mono: PreparedMono, *, name: str, interval_semitones: float, weights: tuple[float, ...], recipe: LadderRecipe
) -> Ladder:
    """A sample read at rates spanning `interval_semitones`, centered on the rate it was stored at.

    Every step is made the way the grid cache makes its retuned views, so a model meets the kind of
    grid it was trained on. Centering keeps each end as close to the stored reading as the interval
    allows, so neither reaches further past the Nyquist frequency than it must.
    """
    steps = [
        recipe.pooled(
            retuned_view(
                mono, semitones=(weight - MIDDLE_WEIGHT) * interval_semitones, canonicalizer=recipe.canonicalizer
            )
        )
        for weight in weights
    ]
    return Ladder(
        family=LadderFamily.RETUNED,
        name=name,
        interval_semitones=interval_semitones,
        weights=weights,
        truth=np.stack(steps),
    )


def synthetic_ladder(ends: SyntheticEnds, *, weights: tuple[float, ...], recipe: LadderRecipe) -> Ladder:
    """A synthetic tone at every weight between two, both of its positions on the geometric line between the ends'."""
    rate_hz = float(recipe.axis.geometry.analysis_rate_hz)
    steps = [
        recipe.pooled(
            recipe.canonicalizer.canonicalize(
                prepare_mono(resonant_tone(ends.first.between(ends.second, weight=weight), rate_hz=rate_hz))
            )
        )
        for weight in weights
    ]
    return Ladder(
        family=ends.family,
        name=ends.name,
        interval_semitones=ends.interval_semitones,
        weights=weights,
        truth=np.stack(steps),
    )


def draw_synthetic_ends(
    family: LadderFamily, *, count: int, intervals: tuple[float, ...], random_seed: int
) -> tuple[SyntheticEnds, ...]:
    """`count` pairs of tones for one synthetic family, drawn by the seed and cycling through the intervals.

    Fundamentals and resonances are drawn evenly in octaves over the range a tracker's leads and
    basses cover and a resonance sits within the bands a reading trusts. Each family draws from a
    stream of its own, so asking for one family does not change the tones another is given.

    Raises:
        ValueError: the family is not a synthetic one.
    """
    if family not in SYNTHETIC_FAMILIES:
        raise _read_from_the_library(family)
    generator = np.random.default_rng([random_seed, SYNTHETIC_FAMILIES.index(family)])
    drawn = []
    for index in range(count):
        interval = intervals[index % len(intervals)]
        start = ResonantTone(
            fundamental_hz=_log_uniform(generator, LOWEST_FUNDAMENTAL_HZ, HIGHEST_FUNDAMENTAL_HZ),
            resonance_hz=_log_uniform(generator, LOWEST_RESONANCE_HZ, HIGHEST_RESONANCE_HZ),
        )
        drawn.append(
            SyntheticEnds(
                family=family,
                name=f"{family.value}-{index:03d}",
                interval_semitones=interval,
                first=start,
                second=_moved(start, family=family, ratio=2.0 ** (interval / SEMITONES_PER_OCTAVE)),
            )
        )
    return tuple(drawn)


def _moved(tone: ResonantTone, *, family: LadderFamily, ratio: float) -> ResonantTone:
    match family:
        case LadderFamily.PITCH:
            return ResonantTone(fundamental_hz=tone.fundamental_hz * ratio, resonance_hz=tone.resonance_hz)
        case LadderFamily.RESONANCE:
            return ResonantTone(fundamental_hz=tone.fundamental_hz, resonance_hz=tone.resonance_hz * ratio)
        case LadderFamily.CONTRARY:
            return ResonantTone(fundamental_hz=tone.fundamental_hz * ratio, resonance_hz=tone.resonance_hz / ratio)
        case LadderFamily.RETUNED | LadderFamily.UNRELATED:
            raise _read_from_the_library(family)


def _read_from_the_library(family: LadderFamily) -> ValueError:
    return ValueError(f"{family.value} ladders are read from the library, not synthesized")


def _log_uniform(generator: np.random.Generator, lowest: float, highest: float) -> float:
    return float(np.exp(generator.uniform(np.log(lowest), np.log(highest))))
