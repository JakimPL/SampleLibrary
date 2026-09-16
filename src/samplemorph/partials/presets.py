from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from samplemorph.partials.profile import MorphProfile, NoCorrespondence, OrderedPartials

DEFAULT_PROFILE_NAME: Final[str] = "slide"
PROFILE_PRESETS: Final[Mapping[str, MorphProfile]] = MappingProxyType(
    {
        "slide": MorphProfile(correspondence=OrderedPartials()),
        "crossfade": MorphProfile(correspondence=NoCorrespondence()),
    }
)
