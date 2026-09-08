from __future__ import annotations

from collections.abc import Callable
from typing import Final

from samplemorph.canonicalizers import Canonicalizer
from samplemorph.canonicalizers.constant_q import build_constant_q_canonicalizer
from samplemorph.canonicalizers.log_frequency import build_log_frequency_canonicalizer
from samplemorph.canonicalizers.mel import build_mel_canonicalizer
from samplemorph.vocoders import Vocoder
from samplemorph.vocoders.griffin_lim import GriffinLimVocoder

DEFAULT_CANONICALIZER_NAME: Final[str] = "log_frequency"
DEFAULT_VOCODER_NAME: Final[str] = "griffin_lim"

CANONICALIZER_REGISTRY: Final[dict[str, Callable[[], Canonicalizer]]] = {
    DEFAULT_CANONICALIZER_NAME: build_log_frequency_canonicalizer,
    "constant_q": build_constant_q_canonicalizer,
    "mel": build_mel_canonicalizer,
}

VOCODER_REGISTRY: Final[dict[str, Callable[[], Vocoder]]] = {
    DEFAULT_VOCODER_NAME: GriffinLimVocoder,
}
