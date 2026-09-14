from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

TIME_BINS: Final[int] = 16
FREQUENCY_BANDS: Final[int] = 8
FINGERPRINT_SIZE: Final[int] = TIME_BINS * FREQUENCY_BANDS
# Every time bin holds at least two frames per band once a waveform spans this many frames.
MINIMUM_FINGERPRINTED_FRAMES: Final[int] = FINGERPRINT_SIZE * 2


def compute_shape_fingerprint(waveform: NDArray[np.float64]) -> NDArray[np.float64]:
    """A coarse, fixed-length descriptor of how a waveform's energy spreads across its time and its frame rate.

    The waveform is split into TIME_BINS equal-duration segments, and each segment's spectrum into
    FREQUENCY_BANDS equal-width bands up to the Nyquist frequency. Two samples holding one sound at
    two gains or depths, or with a few frames of trim between them, read nearly the same descriptor,
    since a gain scales every band alike and a small shift only moves content between adjacent time
    bins. A waveform shorter than ``MINIMUM_FINGERPRINTED_FRAMES`` is read padded with silence to
    that length, so every bin carries a spectrum.

    This is a candidate pre-filter for gain and depth variants, which share a length: it makes a
    nearest-neighbor search over the whole catalog tractable, and the confidence and evidence behind
    any relation it helps surface come from the full-resolution scorer in scoring.py. Silence reads
    as the zero vector, which lies near nothing.
    """
    mono = waveform.mean(axis=1)
    if mono.shape[0] < MINIMUM_FINGERPRINTED_FRAMES:
        mono = np.pad(mono, (0, MINIMUM_FINGERPRINTED_FRAMES - mono.shape[0]))
    features = np.zeros((TIME_BINS, FREQUENCY_BANDS))
    for time_bin, segment in enumerate(_segments(mono)):
        spectrum = np.abs(np.fft.rfft(segment))
        band_edges = np.linspace(0, spectrum.shape[0], FREQUENCY_BANDS + 1).astype(np.int64)
        for band in range(FREQUENCY_BANDS):
            band_start, band_stop = band_edges[band], band_edges[band + 1]
            if band_stop > band_start:
                features[time_bin, band] = np.sqrt(np.mean(spectrum[band_start:band_stop] ** 2))

    return _unit(features)


def compute_rate_fingerprint(waveform: NDArray[np.float64]) -> NDArray[np.float64]:
    """A coarse, fixed-length descriptor of a waveform's energy that a change of sample rate leaves in place.

    Each of the TIME_BINS segments' spectrum is pooled into FREQUENCY_BANDS octave bands counted in
    cycles per segment -- 1 to 2 cycles, 2 to 4, and so on. Counting cycles against the waveform's own
    length is what a resample preserves: stretching a sound to twice the frames keeps every cycle it
    held, so two versions of one sample at different rates read nearly the same descriptor, where the
    shape fingerprint would move every tone by the resampling ratio.

    This is the candidate pre-filter for resampled variants; the scorer in scoring.py decides each
    pair. Silence, and a waveform too short for any segment to hold a cycle, read as the zero vector.
    """
    features = np.zeros((TIME_BINS, FREQUENCY_BANDS))
    for time_bin, segment in enumerate(_segments(waveform.mean(axis=1))):
        spectrum = np.abs(np.fft.rfft(segment))
        for band in range(FREQUENCY_BANDS):
            lowest_cycles, highest_cycles = 2**band, 2 ** (band + 1)
            if lowest_cycles < spectrum.shape[0]:
                features[time_bin, band] = np.sqrt(np.sum(spectrum[lowest_cycles:highest_cycles] ** 2))

    return _unit(features)


def _segments(mono: NDArray[np.float64]) -> list[NDArray[np.float64]]:
    boundaries = np.linspace(0, mono.shape[0], TIME_BINS + 1).astype(np.int64)
    return [mono[boundaries[index] : boundaries[index + 1]] for index in range(TIME_BINS)]


def _unit(features: NDArray[np.float64]) -> NDArray[np.float64]:
    flattened = features.reshape(-1)
    norm = np.linalg.norm(flattened)
    return flattened / norm if norm > 0.0 else flattened
