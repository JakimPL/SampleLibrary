from __future__ import annotations

from collections.abc import Callable
from typing import Final

from samplemorph.canonicalizers import Canonicalizer
from samplemorph.canonicalizers.constant_q import build_constant_q_canonicalizer
from samplemorph.canonicalizers.log_frequency import build_log_frequency_canonicalizer
from samplemorph.canonicalizers.mel import build_mel_canonicalizer
from samplemorph.morphers import Morpher
from samplemorph.morphers.linear import LinearMorpher
from samplemorph.vocoders import Vocoder
from samplemorph.vocoders.griffin_lim import GriffinLimVocoder

DEFAULT_CANONICALIZER_NAME: Final[str] = "log_frequency"
DEFAULT_VOCODER_NAME: Final[str] = "griffin_lim"
DEFAULT_MORPHER_NAME: Final[str] = "linear"

CANONICALIZER_REGISTRY: Final[dict[str, Callable[[], Canonicalizer]]] = {
    DEFAULT_CANONICALIZER_NAME: build_log_frequency_canonicalizer,
    "constant_q": build_constant_q_canonicalizer,
    "mel": build_mel_canonicalizer,
}

SYNTHESIS_CANONICALIZER_NAMES: Final[frozenset[str]] = frozenset({"log_frequency", "mel"})
"""The axes audio is rendered from, whose bands state amplitude per Fourier bin.

A vocoder reads a magnitude as the Fourier magnitude of the signal it is recovering, so an axis
serves synthesis when its bands carry that same quantity. These do, and a round trip through them
lands far nearer its source than an unrelated sample does. `constant_q` measures amplitude per
constant-Q band instead, which makes it the axis that locates a retuning best and keeps it to
analysis.
"""

VOCODER_REGISTRY: Final[dict[str, Callable[[], Vocoder]]] = {
    DEFAULT_VOCODER_NAME: GriffinLimVocoder,
}

MORPHER_REGISTRY: Final[dict[str, Callable[[], Morpher]]] = {
    DEFAULT_MORPHER_NAME: LinearMorpher,
}
