from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from samplemorph.partials.profile import (
    MorphProfile,
    NearestPartials,
    NoCorrespondence,
    NotesCorrespondence,
    OrderedPartials,
)

DEFAULT_PROFILE_NAME: Final[str] = "glide"
PROFILE_PRESETS: Final[Mapping[str, MorphProfile]] = MappingProxyType(
    {
        "glide": MorphProfile(correspondence=NotesCorrespondence()),
        "pivot": MorphProfile(correspondence=NearestPartials()),
        "slide": MorphProfile(correspondence=OrderedPartials()),
        "crossfade": MorphProfile(correspondence=NoCorrespondence()),
    }
)
