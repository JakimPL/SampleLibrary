from __future__ import annotations

from enum import StrEnum, unique
from typing import Annotated, Final, Literal

from pydantic import BaseModel, Field, model_validator

from samplecore.models.base import FROZEN
from samplemorph.partials.paths import FadeLaw, PitchPath, TimbrePath

DEFAULT_CAP_SEMITONES: Final[float] = 12.0
DEFAULT_MOVEMENT_EXPONENT: Final[float] = 2.0
DEFAULT_CAP_CENTS: Final[float] = 100.0
DEFAULT_COMMON_CENTS: Final[float] = 50.0


class NotesCorrespondence(BaseModel):
    """Notes meet note to note, harmonic to harmonic, and a note with no partner fades.

    Which note meets which is the pairing that costs the least over the whole chord, a move costing
    what the two notes carry times how far they travel raised to `exponent`, and a note fading
    costing what it carries times `cap_semitones` raised to the same power. Above the first power
    several short moves cost less than one long one, so a chord's voices move in order and the
    movement spreads across them. Partials standing free of every note meet by pitch, each pair the
    nearest to the other within `cap_cents`.
    """

    model_config = FROZEN

    kind: Literal["notes"] = "notes"
    cap_semitones: float = Field(default=DEFAULT_CAP_SEMITONES, gt=0.0)
    exponent: float = Field(default=DEFAULT_MOVEMENT_EXPONENT, gt=0.0)
    cap_cents: float = Field(default=DEFAULT_CAP_CENTS, gt=0.0)


class NearestPartials(BaseModel):
    """Partials meet by pitch alone, each pair the nearest to the other within `cap_cents`.

    A quarter tone apart is near enough to be the same partial heard twice, so what the two sounds
    hold in common holds still while everything else fades where it stands: the middle a listener
    hears as one sound turning into another through what they share.
    """

    model_config = FROZEN

    kind: Literal["nearest"] = "nearest"
    cap_cents: float = Field(default=DEFAULT_COMMON_CENTS, gt=0.0)


class OrderedPartials(BaseModel):
    """Partials meet in frequency order, one to one, and whichever are left over fade.

    Each partial of one sound slides to a partial of the other, the pairs keeping their order in
    frequency, so every partial arrives whole and the set arrives spread as it started.
    """

    model_config = FROZEN

    kind: Literal["ordered"] = "ordered"


class NoCorrespondence(BaseModel):
    """Every partial keeps its own frequency, one sound's fading out as the other's fade in.

    It is the crossfade a morph is judged against, drawn by the same oscillators as every other
    profile, so what a comparison shows is what moving the partials adds.
    """

    model_config = FROZEN

    kind: Literal["none"] = "none"


Correspondence = Annotated[
    NotesCorrespondence | NearestPartials | OrderedPartials | NoCorrespondence, Field(discriminator="kind")
]


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
