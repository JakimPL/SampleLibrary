from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

SAMPLE_RATE: Final[int] = 44100
HARMONIC_COUNT: Final[int] = 5
DECAY_PER_SECOND: Final[float] = 8.0


def tonal_waveform(frame_count: int, *, frequency: float, seed: int) -> NDArray[np.float64]:
    """A smooth, band-limited waveform: `HARMONIC_COUNT` harmonics of `frequency`, at random relative
    weights and phases drawn from `seed`.

    A fixed harmonic ratio is not enough to keep unrelated scenarios apart: two tones sharing the
    same relative harmonic weights are, at some resampling ratio, numerically indistinguishable --
    resampling scales every harmonic by the same factor, so it can reproduce one tone's frequency
    from another's exactly. Randomizing the weights per `seed` instead gives each scenario its own
    spectral shape, which a resampling ratio cannot reproduce from a different scenario's shape, so
    independently seeded waveforms stay apart under the same fingerprint search this library's own
    detectors use. A deliberate pair still shares one identical waveform (weights included) before
    its own transformation is applied, so the relationship a pair is built to demonstrate is
    unaffected.
    """
    time = np.arange(frame_count) / SAMPLE_RATE
    random_generator = np.random.default_rng(seed)
    harmonics = np.arange(1, HARMONIC_COUNT + 1)
    weights = random_generator.uniform(0.2, 1.0, size=harmonics.shape)
    weights /= np.sum(weights)
    phases = random_generator.uniform(0.0, 2 * np.pi, size=harmonics.shape)
    tone: NDArray[np.float64] = np.zeros(frame_count)
    for harmonic, weight, phase in zip(harmonics, weights, phases):
        tone += weight * np.sin(2 * np.pi * frequency * harmonic * time + phase)

    return tone


def resample_stable_waveform(frame_count: int, *, frequency: float) -> NDArray[np.float64]:
    """A waveform for the resampled-variant pair specifically, whose harmonic shape is fixed rather
    than randomized, at this function's own default frequency (440 Hz, matching the call site below).

    Checked empirically while building this corpus: `compute_fingerprint`'s candidate-generation
    similarity depends on more than the resampling ratio alone -- this exact three-harmonic ratio
    stays above the 0.95 candidate-generation threshold at 440 Hz (matching
    `tests/sampleextract/equivalence/test_fingerprint.py`'s own proof of that), a random
    harmonic-weight distribution fell well under it regardless of frequency, and even this fixed
    ratio fell under it at a different frequency tried while building this corpus (990 Hz) -- the
    confirmatory scorer still matched every one of these correctly once compared directly, so this
    is a fragility of the coarse candidate-generation prefilter, not the underlying detection. The
    resampled pair needs to survive candidate generation to demonstrate anything, so it keeps to the
    frequency already verified to.
    """
    time = np.arange(frame_count) / SAMPLE_RATE
    return (
        0.5 * np.sin(2 * np.pi * frequency * time)
        + 0.3 * np.sin(2 * np.pi * frequency * 2 * time)
        + 0.2 * np.sin(2 * np.pi * frequency * 4 * time)
    )


def decaying(waveform: NDArray[np.float64], *, rate: int) -> NDArray[np.float64]:
    """A waveform fading out the way a struck sound does, at a fixed rate per second."""
    envelope = np.exp(-DECAY_PER_SECOND * np.arange(waveform.shape[0]) / rate)
    decayed: NDArray[np.float64] = 0.9 * waveform * envelope
    return decayed
