from __future__ import annotations

from typing import Final

import numpy as np

from samplemorph.partials.tracks import CENTS_PER_OCTAVE, PartialTracks

LOUDNESS_EXPONENT: Final[float] = 0.6


def partial_wobble_cents(tracks: PartialTracks) -> float:
    """How far a sound's partials move in pitch every 3 ms as heard, in cents, counted by how loud they are.

    A step counts by the quieter of its two frames' amplitudes to the power of 0.6, the loudness of
    its energy. A steady note reads a few tenths of a cent, a natural vibrato a few cents, and a morph
    whose partials jitter from frame to frame far more than either of its ends. A sound holding no
    partial reads not a number.
    """
    if tracks.track_count == 0 or tracks.frame_count < 2:
        return float("nan")

    frequency = tracks.frequency_hz.astype(np.float64)
    amplitude = tracks.amplitude.astype(np.float64)
    steps = np.abs(CENTS_PER_OCTAVE * np.log2(frequency[:, 1:] / frequency[:, :-1]))
    weights = np.minimum(amplitude[:, 1:], amplitude[:, :-1]) ** LOUDNESS_EXPONENT
    total = float(weights.sum())
    return float((steps * weights).sum() / total) if total > 0.0 else float("nan")
