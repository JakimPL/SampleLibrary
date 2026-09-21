from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplecore.auditory.envelope import local_rms_envelope

STRIKE_RISE_DB: Final[float] = 12.0
STRIKE_LOOKBACK_SECONDS: Final[float] = 0.02
MAIN_STRIKE_DEPTH_DB: Final[float] = 12.0


@dataclass(frozen=True)
class Strikes:
    """A clip's local level cut into strikes, each beginning where the level climbs `STRIKE_RISE_DB` within `STRIKE_LOOKBACK_SECONDS`.

    The first strike begins at the clip's start, so the strikes cover every point exactly once, and
    a loop of hits reads hit by hit. The level travels beside the cut, linear and in decibels under
    the clip's peak, since every reader weighs or scores a strike by it.
    """

    level: NDArray[np.float64]
    decibels: NDArray[np.float64]
    starts: NDArray[np.intp]
    ends: NDArray[np.intp]


def read_strikes(mono: NDArray[np.float64], *, sample_rate_hz: int) -> Strikes:
    """Cut a mono waveform into strikes at the rate its frames are heard at."""
    level = local_rms_envelope(mono, sample_rate_hz=sample_rate_hz)
    decibels = 20.0 * np.log10(level / float(level.max()))
    lookback = max(int(STRIKE_LOOKBACK_SECONDS * sample_rate_hz), 1)
    rise = decibels[lookback:] - decibels[:-lookback]
    climbing = np.concatenate((np.zeros(lookback, dtype=bool), rise >= STRIKE_RISE_DB))
    onsets = np.flatnonzero(climbing[1:] & ~climbing[:-1]) + 1
    return Strikes(
        level=level,
        decibels=decibels,
        starts=np.concatenate(([0], onsets)).astype(np.intp),
        ends=np.concatenate((onsets, [decibels.shape[0]])).astype(np.intp),
    )


def main_onset(mono: NDArray[np.float64], *, sample_rate_hz: int) -> int:
    """The point where a clip's main strike begins to sound.

    The main strike is the first whose peak comes within `MAIN_STRIKE_DEPTH_DB` of the clip's own
    peak, so a quiet pickup before a hit leaves the hit as the main strike. Its onset is the first
    point of that strike within `MAIN_STRIKE_DEPTH_DB` of the strike's peak, which places a sharp hit
    at its attack and a slow swell where it has risen most of the way.
    """
    strikes = read_strikes(mono, sample_rate_hz=sample_rate_hz)
    peaks = np.maximum.reduceat(strikes.decibels, strikes.starts)
    main = int(np.flatnonzero(peaks >= -MAIN_STRIKE_DEPTH_DB)[0])
    start, end = int(strikes.starts[main]), int(strikes.ends[main])
    span = strikes.decibels[start:end]
    return start + int(np.flatnonzero(span >= float(peaks[main]) - MAIN_STRIKE_DEPTH_DB)[0])
