from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.partials.peaks import analysis_length, gaussian_transform, pick_peaks
from samplemorph.partials.settings import PartialSettings
from samplemorph.partials.tracks import CENTS_PER_OCTAVE, track_peaks

WOBBLE_HOP_SECONDS: Final[float] = 0.003
WOBBLE_MINIMUM_TRACK_SECONDS: Final[float] = 0.1
WOBBLE_DEPTH_DB: Final[float] = 40.0
LOUDNESS_EXPONENT: Final[float] = 0.6
WOBBLE_SETTINGS: Final[PartialSettings] = PartialSettings(
    minimum_track_seconds=WOBBLE_MINIMUM_TRACK_SECONDS, peak_depth_db=WOBBLE_DEPTH_DB
)


def partial_wobble_cents(waveform: NDArray[np.float64], *, rate_hz: float) -> float:
    """How far a waveform's partials move in pitch every 3 ms as heard, in cents, counted by how loud they are.

    The partials are the tracks of at least 100 ms within 40 dB of each frame's loudest peak, and a
    step counts by the quieter of its two frames' amplitudes to the power of 0.6, the loudness of its
    energy. A steady note reads a few tenths of a cent, a natural vibrato a few cents, and a morph whose
    partials jitter from frame to frame far more than either of its ends. A waveform holding no
    partial reads not a number.
    """
    hop_length = max(int(round(WOBBLE_HOP_SECONDS * rate_hz)), 1)
    window_length = analysis_length(rate_hz, settings=WOBBLE_SETTINGS)
    peaks = pick_peaks(
        gaussian_transform(waveform, window_length=window_length, hop_length=hop_length),
        rate_hz=rate_hz,
        window_length=window_length,
        settings=WOBBLE_SETTINGS,
    )
    tracks = track_peaks(peaks, hop_length=hop_length, rate_hz=rate_hz, settings=WOBBLE_SETTINGS)
    if tracks.track_count == 0 or tracks.frame_count < 2:
        return float("nan")

    frequency = tracks.frequency_hz.astype(np.float64)
    amplitude = tracks.amplitude.astype(np.float64)
    steps = np.abs(CENTS_PER_OCTAVE * np.log2(frequency[:, 1:] / frequency[:, :-1]))
    weights = np.minimum(amplitude[:, 1:], amplitude[:, :-1]) ** LOUDNESS_EXPONENT
    total = float(weights.sum())
    return float((steps * weights).sum() / total) if total > 0.0 else float("nan")
