from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

TIME_BINS: Final[int] = 16
FREQUENCY_BANDS: Final[int] = 8


def compute_fingerprint(waveform: NDArray[np.float64]) -> NDArray[np.float64]:
    """A coarse, fixed-length descriptor of a waveform's energy across time and frequency.

    Splitting the waveform into TIME_BINS equal-duration segments, and each segment's own
    spectrum into FREQUENCY_BANDS equal-width bands, gives a descriptor that is directly
    comparable between two samples of any length or implied rate -- unlike a raw waveform or a
    single whole-signal spectrum, it stays close to unchanged under the few frames of lead-in or
    trim difference two independent exports of the same content commonly carry, since a small
    shift only moves content between adjacent time bins rather than corrupting the whole
    descriptor. This is a candidate pre-filter only: it exists to make a spatial nearest-neighbor
    search over the whole catalog tractable, and the confidence and evidence behind any relation
    it helps surface always come from the full-resolution scorer in scoring.py, never from here.
    """
    mono = waveform.mean(axis=1)
    boundaries = np.linspace(0, mono.shape[0], TIME_BINS + 1).astype(np.int64)
    features = np.zeros((TIME_BINS, FREQUENCY_BANDS))
    for time_bin in range(TIME_BINS):
        segment = mono[boundaries[time_bin] : boundaries[time_bin + 1]]
        if segment.shape[0] < FREQUENCY_BANDS * 2:
            continue

        spectrum = np.abs(np.fft.rfft(segment))
        band_edges = np.linspace(0, spectrum.shape[0], FREQUENCY_BANDS + 1).astype(np.int64)
        for band in range(FREQUENCY_BANDS):
            band_start, band_stop = band_edges[band], band_edges[band + 1]
            if band_stop > band_start:
                features[time_bin, band] = np.sqrt(np.mean(spectrum[band_start:band_stop] ** 2))

    flattened = features.reshape(-1)
    norm = np.linalg.norm(flattened)
    return flattened / norm if norm > 0.0 else flattened
