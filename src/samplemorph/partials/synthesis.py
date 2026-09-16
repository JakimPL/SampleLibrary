from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.partials.tracks import PartialTracks

BLOCK_SAMPLES: Final[int] = 16384
QUIET_PARTIAL_DB: Final[float] = 80.0
NYQUIST_TAPER_START: Final[float] = 0.46
NYQUIST_TAPER_END: Final[float] = 0.48
LOWEST_HEARD_HZ: Final[float] = 20.0
HEARD_RAMP_HZ: Final[float] = 10.0
TURN: Final[float] = 2.0 * np.pi


def oscillate(tracks: PartialTracks, *, sample_count: int) -> NDArray[np.float64]:
    """Sound every partial as an oscillator of its own, each following its frequency and amplitude sample by sample.

    Between two frames a partial's frequency and amplitude run straight from one to the other, and
    its phase is carried on from wherever it stood, so a partial gliding over a whole sound stays one
    unbroken tone. A partial fades out as it approaches the rate's own ceiling and where it falls
    under what is heard as pitch, which leaves the result within the band the rate carries. Partials
    quieter than `QUIET_PARTIAL_DB` under the loudest stay silent, which keeps the work to what a
    listener hears.
    """
    waveform = np.zeros(sample_count, dtype=np.float64)
    if tracks.track_count == 0 or sample_count <= 0:
        return waveform

    phases = np.zeros(tracks.track_count, dtype=np.float64)
    audible = float(tracks.amplitude.max()) * 10.0 ** (-QUIET_PARTIAL_DB / 20.0)
    for start in range(0, sample_count, BLOCK_SAMPLES):
        stop = min(start + BLOCK_SAMPLES, sample_count)
        positions = np.arange(start, stop, dtype=np.float64) / tracks.hop_length
        lower = np.minimum(positions.astype(np.int64), tracks.frame_count - 1)
        upper = np.minimum(lower + 1, tracks.frame_count - 1)
        sounding = np.flatnonzero(tracks.amplitude[:, lower[0] : upper[-1] + 1].max(axis=1) > audible)
        if sounding.size == 0:
            continue

        share = positions - lower
        amplitude = _between(tracks.amplitude[sounding], lower=lower, upper=upper, share=share)
        frequency = _between(tracks.frequency_hz[sounding], lower=lower, upper=upper, share=share)
        phase = phases[sounding, None] + TURN * np.cumsum(frequency, axis=1) / tracks.rate_hz
        waveform[start:stop] = (amplitude * _heard_gain(frequency, rate_hz=tracks.rate_hz) * np.sin(phase)).sum(axis=0)
        phases[sounding] = np.mod(phase[:, -1], TURN)
    return waveform


def _between(
    frames: NDArray[np.float32], *, lower: NDArray[np.int64], upper: NDArray[np.int64], share: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Each row read at every sample between two frames. Shapes: `frames` is ``(rows, frames)``, the result ``(rows, samples)``."""
    read: NDArray[np.float64] = (
        frames[:, lower].astype(np.float64) * (1.0 - share) + frames[:, upper].astype(np.float64) * share
    )
    return read


def _heard_gain(frequency: NDArray[np.float64], *, rate_hz: float) -> NDArray[np.float64]:
    """How much of a partial is sounded at each frequency: all of it over the heard band, and none outside it."""
    below_ceiling = (NYQUIST_TAPER_END * rate_hz - frequency) / ((NYQUIST_TAPER_END - NYQUIST_TAPER_START) * rate_hz)
    over_floor = (frequency - LOWEST_HEARD_HZ) / HEARD_RAMP_HZ
    gain: NDArray[np.float64] = np.clip(below_ceiling, 0.0, 1.0) * np.clip(over_floor, 0.0, 1.0)
    return gain
