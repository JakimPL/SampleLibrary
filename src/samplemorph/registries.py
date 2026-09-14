from __future__ import annotations

from collections.abc import Callable
from typing import Final, Protocol

from samplemorph.canonicalizers import Canonicalizer
from samplemorph.canonicalizers.constant_q import ConstantQCanonicalizer, build_constant_q_canonicalizer
from samplemorph.canonicalizers.log_frequency import LogFrequencyCanonicalizer, build_log_frequency_canonicalizer
from samplemorph.canonicalizers.mel import MelCanonicalizer, build_mel_canonicalizer
from samplemorph.geometry import DEFAULT_ANCHOR, Anchor, ConstantQGeometry, Geometry, LogFrequencyGeometry, MelGeometry
from samplemorph.morphers import Morpher
from samplemorph.morphers.linear import LinearMorpher
from samplemorph.vocoders import Vocoder
from samplemorph.vocoders.pghi import PghiVocoder

DEFAULT_CANONICALIZER_NAME: Final[str] = "log_frequency"
PGHI_VOCODER_NAME: Final[str] = "pghi"
RESTORED_VOCODER_NAME: Final[str] = "restored"
DEFAULT_VOCODER_NAME: Final[str] = RESTORED_VOCODER_NAME
DEFAULT_MORPHER_NAME: Final[str] = "linear"


class CanonicalizerFactory(Protocol):
    """Builds one frequency axis's canonicalizer, on the anchor rule a run asks for."""

    def __call__(self, *, anchor: Anchor = DEFAULT_ANCHOR) -> Canonicalizer: ...


CANONICALIZER_REGISTRY: Final[dict[str, CanonicalizerFactory]] = {
    DEFAULT_CANONICALIZER_NAME: build_log_frequency_canonicalizer,
    "constant_q": build_constant_q_canonicalizer,
    "mel": build_mel_canonicalizer,
}

RENDERABLE_CANONICALIZER_NAMES: Final[frozenset[str]] = frozenset({DEFAULT_CANONICALIZER_NAME})
"""The axes a model fitted on them can be heard from: a log-frequency analysis under a Gaussian taper.

Every vocoder that renders a morph integrates a phase for that analysis, so a codec or a restorer
fitted on another axis stores a model nothing can play.
"""

VOCODER_REGISTRY: Final[dict[str, Callable[[], Vocoder]]] = {
    PGHI_VOCODER_NAME: PghiVocoder,
}
"""The vocoders a name alone builds: phase gradient heap integration on the grid as it is.

`RESTORED_VOCODER_NAME`, the production path, stays out of it: it reads a fitted restorer from a
file under the library root, so the caller supplies where to read it from rather than a factory
guessing.
"""

MORPHER_REGISTRY: Final[dict[str, Callable[[], Morpher]]] = {
    DEFAULT_MORPHER_NAME: LinearMorpher,
}


def canonicalizer_for_geometry(geometry: Geometry) -> Canonicalizer:
    """The canonicalizer that reads exactly this geometry, for rebuilding the axis a stored model was fitted on."""
    match geometry:
        case LogFrequencyGeometry():
            return LogFrequencyCanonicalizer(geometry)
        case MelGeometry():
            return MelCanonicalizer(geometry)
        case ConstantQGeometry():
            return ConstantQCanonicalizer(geometry)
