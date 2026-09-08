from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def fold_to_mono(waveform: NDArray[np.float64]) -> NDArray[np.float64]:
    """Average a waveform's channels into one, passing an already-mono signal through unchanged."""
    return waveform.mean(axis=1) if waveform.ndim > 1 else waveform


def remove_dc_offset(mono: NDArray[np.float64]) -> NDArray[np.float64]:
    """Subtract a mono signal's own mean, correcting a constant recording-chain bias.

    An off-center signal registers as spurious low-frequency energy in a spectral analysis and
    skews an RMS-based envelope reading; a signal already centered passes through unaffected, since
    its mean already sits at or near zero.
    """
    return mono - mono.mean()
