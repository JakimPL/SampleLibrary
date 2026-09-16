from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from samplecore.models.base import FROZEN


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


Correspondence = Annotated[OrderedPartials | NoCorrespondence, Field(discriminator="kind")]


class MorphProfile(BaseModel):
    """What the middle of two sounds is: who meets whom on the way.

    A profile is read once for a whole path, so every point between two sounds follows one
    correspondence, and a render can name the profile it took.
    """

    model_config = FROZEN

    correspondence: Correspondence
