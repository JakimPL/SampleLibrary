from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from samplemorph.partials.paths import PitchPath
from samplemorph.partials.profile import (
    AspectCurve,
    AspectCurves,
    CurveShape,
    MorphProfile,
    NearestPartials,
    NoCorrespondence,
    NotesCorrespondence,
    OrderedPartials,
)

DEFAULT_PROFILE_NAME: Final[str] = "glide"
EASED_START: Final[float] = 0.25
EASED_END: Final[float] = 0.75
PROFILE_PRESETS: Final[Mapping[str, MorphProfile]] = MappingProxyType(
    {
        "glide": MorphProfile(correspondence=NotesCorrespondence()),
        "stepped": MorphProfile(correspondence=NotesCorrespondence(), pitch=PitchPath.STEPPED),
        "eased": MorphProfile(
            correspondence=NotesCorrespondence(),
            curves=AspectCurves(pitch=AspectCurve(start=EASED_START, end=EASED_END, shape=CurveShape.EASED)),
        ),
        "switch": MorphProfile(correspondence=NotesCorrespondence(), pitch=PitchPath.SWITCH),
        "pivot": MorphProfile(correspondence=NearestPartials()),
        "slide": MorphProfile(correspondence=OrderedPartials()),
        "crossfade": MorphProfile(correspondence=NoCorrespondence()),
    }
)
