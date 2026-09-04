from __future__ import annotations

from enum import IntEnum, unique


@unique
class ChannelLayout(IntEnum):
    """How many interleaved channels one frame of a Sample's waveform carries."""

    MONO = 1
    STEREO = 2
