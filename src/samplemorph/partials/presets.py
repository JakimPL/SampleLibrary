from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from samplemorph.partials.paths import PitchPath
from samplemorph.partials.profile import (
    AspectCurve,
    AspectCurves,
    Correspondence,
    CorrespondenceUnit,
    CurveShape,
    MorphProfile,
)

DEFAULT_PROFILE_NAME: Final[str] = "glide"
EASED_START: Final[float] = 0.25
EASED_END: Final[float] = 0.75
COMMON_CENTS: Final[float] = 50.0
HELD_FADE_PRICE: Final[float] = 1000.0
FREE_FADE_PRICE: Final[float] = 0.0
NO_SHIFTS: Final[int] = 0
NO_WEIGHT: Final[float] = 0.0
TRAVELS: Final[Correspondence] = Correspondence()
TRAVELS_AS_OBJECTS: Final[Correspondence] = Correspondence(unit=CorrespondenceUnit.GROUPS)
HOLDS_WHAT_IS_SHARED: Final[Correspondence] = Correspondence(
    travel_cents=COMMON_CENTS, largest_shift_count=NO_SHIFTS, level_weight=NO_WEIGHT, lifetime_weight=NO_WEIGHT
)
SLIDES_IN_ORDER: Final[Correspondence] = Correspondence(
    fade_price=HELD_FADE_PRICE, largest_shift_count=NO_SHIFTS, level_weight=NO_WEIGHT, lifetime_weight=NO_WEIGHT
)
FADES_IN_PLACE: Final[Correspondence] = Correspondence(fade_price=FREE_FADE_PRICE)
PROFILE_PRESETS: Final[Mapping[str, MorphProfile]] = MappingProxyType(
    {
        "glide": MorphProfile(correspondence=TRAVELS),
        "stepped": MorphProfile(correspondence=TRAVELS, pitch=PitchPath.STEPPED),
        "eased": MorphProfile(
            correspondence=TRAVELS,
            curves=AspectCurves(pitch=AspectCurve(start=EASED_START, end=EASED_END, shape=CurveShape.EASED)),
        ),
        "switch": MorphProfile(correspondence=TRAVELS, pitch=PitchPath.SWITCH),
        "rigid": MorphProfile(correspondence=TRAVELS_AS_OBJECTS),
        "pivot": MorphProfile(correspondence=HOLDS_WHAT_IS_SHARED),
        "slide": MorphProfile(correspondence=SLIDES_IN_ORDER),
        "crossfade": MorphProfile(correspondence=FADES_IN_PLACE),
    }
)
