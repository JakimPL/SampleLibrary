from __future__ import annotations

from typing import Final, Protocol

from sampledescriptor.canonicalizers import Canonicalizer
from sampledescriptor.canonicalizers.log_frequency import LogFrequencyCanonicalizer, build_log_frequency_canonicalizer
from samplemorph.geometry import DEFAULT_ANCHOR, Anchor, LogFrequencyGeometry

DEFAULT_CANONICALIZER_NAME: Final[str] = "log_frequency"


class CanonicalizerFactory(Protocol):
    """Builds one frequency axis's canonicalizer, on the anchor rule a run asks for."""

    def __call__(self, *, anchor: Anchor = DEFAULT_ANCHOR) -> Canonicalizer: ...


CANONICALIZER_REGISTRY: Final[dict[str, CanonicalizerFactory]] = {
    DEFAULT_CANONICALIZER_NAME: build_log_frequency_canonicalizer,
}


def canonicalizer_for_geometry(geometry: LogFrequencyGeometry) -> Canonicalizer:
    """The canonicalizer that reads exactly this geometry, for rebuilding the axis a stored model was fitted on."""
    return LogFrequencyCanonicalizer(geometry)
