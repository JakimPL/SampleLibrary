from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.partials.peaks import analysis_length, gaussian_transform, pick_peaks
from samplemorph.partials.settings import PartialSettings
from samplemorph.partials.tracks import PartialTracks, track_peaks

HEARD_HOP_SECONDS: Final[float] = 0.003
HEARD_MINIMUM_TRACK_SECONDS: Final[float] = 0.1
HEARD_DEPTH_DB: Final[float] = 40.0
HEARD_SETTINGS: Final[PartialSettings] = PartialSettings(
    minimum_track_seconds=HEARD_MINIMUM_TRACK_SECONDS, peak_depth_db=HEARD_DEPTH_DB
)


def heard_partials(waveform: NDArray[np.float64], *, rate_hz: float) -> PartialTracks:
    """The partials a rendered sound holds, read every 3 ms as heard, which is what a reading of its pitch rests on.

    The partials are the tracks of at least 100 ms standing within 40 dB of each frame's loudest
    peak, read once so that every reading of a point takes the same partials.
    """
    hop_length = max(int(round(HEARD_HOP_SECONDS * rate_hz)), 1)
    window_length = analysis_length(rate_hz, settings=HEARD_SETTINGS)
    peaks = pick_peaks(
        gaussian_transform(waveform, window_length=window_length, hop_length=hop_length),
        rate_hz=rate_hz,
        window_length=window_length,
        settings=HEARD_SETTINGS,
    )
    return track_peaks(peaks, hop_length=hop_length, rate_hz=rate_hz, settings=HEARD_SETTINGS)
