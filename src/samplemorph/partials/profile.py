from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import BaseModel, Field

from samplecore.models.base import FROZEN

DEFAULT_CAP_SEMITONES: Final[float] = 12.0
DEFAULT_MOVEMENT_EXPONENT: Final[float] = 2.0
DEFAULT_CAP_CENTS: Final[float] = 100.0


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

    What the two sounds hold in common holds still, and everything else fades where it stands, which
    is the middle a listener hears as one sound turning into another through what they share.
    """

    model_config = FROZEN

    kind: Literal["nearest"] = "nearest"
    cap_cents: float = Field(default=DEFAULT_CAP_CENTS, gt=0.0)


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


class MorphProfile(BaseModel):
    """What the middle of two sounds is: who meets whom on the way.

    A profile is read once for a whole path, so every point between two sounds follows one
    correspondence, and a render can name the profile it took.
    """

    model_config = FROZEN

    correspondence: Correspondence
