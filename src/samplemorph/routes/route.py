from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from samplecore.waveform import heard_at_rate
from samplemorph.canonicalizers.common import PreparedMono, prepare_mono


@dataclass(frozen=True)
class HeardMono:
    """One end of a pair as it sounds in the pair's frame: prepared frames played at `rate_hz`."""

    mono: PreparedMono
    rate_hz: float


def hear_in_frame(pcm: NDArray[np.float64], *, rate_hz: float, target_rate_hz: float) -> HeardMono:
    """Stored frames heard at `rate_hz`, resampled so that played at `target_rate_hz` they sound the same."""
    return HeardMono(
        mono=prepare_mono(heard_at_rate(pcm, playback_rate_hz=rate_hz, stored_rate_hz=target_rate_hz)),
        rate_hz=target_rate_hz,
    )
