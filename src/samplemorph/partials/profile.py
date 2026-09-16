from __future__ import annotations

from enum import StrEnum, unique
from typing import Final

from pydantic import BaseModel, Field, model_validator

from samplecore.models.base import FROZEN
from samplemorph.partials.paths import FadeLaw, PitchPath, TimbrePath

DEFAULT_TRAVEL_CENTS: Final[float] = 2400.0
DEFAULT_DRIFT_CENTS: Final[float] = 300.0
DEFAULT_LEVEL_WEIGHT: Final[float] = 0.0
DEFAULT_LIFETIME_WEIGHT: Final[float] = 0.1
DEFAULT_MOVEMENT_EXPONENT: Final[float] = 2.0
DEFAULT_FADE_PRICE: Final[float] = 1.0
DEFAULT_LARGEST_SHIFT_COUNT: Final[int] = 4
DEFAULT_SHIFT_SPREAD_CENTS: Final[float] = 20.0


@unique
class CorrespondenceUnit(StrEnum):
    """What travels between two sounds.

    `PARTIALS` lets every channel find its own partner and its own path, which follows a sound
    closely wherever its partials were read cleanly. `GROUPS` sends whole objects — a note's
    harmonics, or a set of partials rising and falling together — along one move each, so a tone
    arrives as one tone however its partials were read, and the morph has as many free choices as the
    sounds have objects rather than as many as they have partials.
    """

    PARTIALS = "partials"
    GROUPS = "groups"


class Correspondence(BaseModel):
    """Which partial of one sound meets which of the other, priced so that every partial has both choices.

    A partial may travel to one partial of the other sound or fade where it stands, and the pairing
    taken is the one whose price over both sounds is least. Travelling costs four things, each
    reaching 1 where it alone is worth a whole fade: the distance covered against `travel_cents`, the
    distance by which that move stands apart from the moves the two sounds agree on against
    `drift_cents`, a difference in loudness against `level_weight`, and time heard apart against
    `lifetime_weight`. The first two are raised to `exponent`, above the first power so that several
    short moves come cheaper than one long one and a chord's movement spreads over its voices. A
    partial fades at `fade_price`, so a high price sends partials travelling far and a low one holds
    still what the two sounds already share.

    The moves two sounds agree on are read as the heaviest `largest_shift_count` peaks of the weight
    their partials put on each interval, spread over `shift_spread_cents`. Reading them is what pairs
    a harmonic series as a series and a chord voice by voice, on one rule that asks the sound nothing
    about its notes. `unit` says what the pairing is made of: single partials, or whole objects
    travelling by one move each, for which `travel_cents` and `fade_price` are read the same way.
    """

    model_config = FROZEN

    unit: CorrespondenceUnit = CorrespondenceUnit.PARTIALS
    travel_cents: float = Field(default=DEFAULT_TRAVEL_CENTS, gt=0.0)
    drift_cents: float = Field(default=DEFAULT_DRIFT_CENTS, gt=0.0)
    level_weight: float = Field(default=DEFAULT_LEVEL_WEIGHT, ge=0.0)
    lifetime_weight: float = Field(default=DEFAULT_LIFETIME_WEIGHT, ge=0.0)
    exponent: float = Field(default=DEFAULT_MOVEMENT_EXPONENT, gt=0.0)
    fade_price: float = Field(default=DEFAULT_FADE_PRICE, ge=0.0)
    largest_shift_count: int = Field(default=DEFAULT_LARGEST_SHIFT_COUNT, ge=0)
    shift_spread_cents: float = Field(default=DEFAULT_SHIFT_SPREAD_CENTS, gt=0.0)

    @property
    def travel_reach_cents(self) -> float:
        """How far a partial agreeing with the moves the two sounds make will travel before fading comes cheaper."""
        return float(self.travel_cents * self.fade_price ** (1.0 / self.exponent))


@unique
class CurveShape(StrEnum):
    """How an aspect moves over the stretch of the path it moves on.

    `LINEAR` moves evenly across it, and `EASED` leaves rest and arrives at rest, which holds a pitch
    near each end for longer and crosses the middle faster.
    """

    LINEAR = "linear"
    EASED = "eased"


class AspectCurve(BaseModel):
    """When one aspect of a morph moves: it holds until `start`, moves to `end`, and is there after it.

    Every aspect reads the one weight of the morph through a curve of its own, so a profile can move
    pitch over the middle of the path while level moves across the whole of it. Both ends of the
    morph stay exact: at weight 0 the curve reads 0 and at weight 1 it reads 1.

    Raises:
        ValueError: `start` stands at or past `end`.
    """

    model_config = FROZEN

    start: float = Field(default=0.0, ge=0.0, lt=1.0)
    end: float = Field(default=1.0, gt=0.0, le=1.0)
    shape: CurveShape = CurveShape.LINEAR

    @model_validator(mode="after")
    def _rises(self) -> AspectCurve:
        if self.start >= self.end:
            raise ValueError(
                f"an aspect moves from a start under its end, and {self.start} stands at or past {self.end}"
            )
        return self

    def at(self, weight: float) -> float:
        """How far this aspect has moved when the morph stands at `weight`."""
        share = min(max((weight - self.start) / (self.end - self.start), 0.0), 1.0)
        match self.shape:
            case CurveShape.LINEAR:
                return share
            case CurveShape.EASED:
                return float(share * share * (3.0 - 2.0 * share))


class AspectCurves(BaseModel):
    """The curve every aspect of a morph moves along: its pitch, its timbre, its level, its time and its residual."""

    model_config = FROZEN

    pitch: AspectCurve = AspectCurve()
    timbre: AspectCurve = AspectCurve()
    level: AspectCurve = AspectCurve()
    time: AspectCurve = AspectCurve()
    residual: AspectCurve = AspectCurve()


class MorphProfile(BaseModel):
    """What the middle of two sounds is: who meets whom on the way, how each of them travels, and when.

    A profile is read once for a whole path, so every point between two sounds follows one
    correspondence and one set of paths, and a render can name the profile it took.
    """

    model_config = FROZEN

    correspondence: Correspondence
    pitch: PitchPath = PitchPath.GLIDE
    timbre: TimbrePath = TimbrePath.WITH_PARTIALS
    fade: FadeLaw = FadeLaw.LEVEL_PATH
    curves: AspectCurves = AspectCurves()
