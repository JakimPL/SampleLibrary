from __future__ import annotations

import warnings
from typing import Final, Protocol

import librosa
import numpy as np
from numpy.typing import NDArray

from samplemorph.canonicalizers.common import SHORT_SIGNAL_WARNING, PreparedMono

CONSTANT_Q_WINDOW: Final[str] = "hann"


class ConstantQAxis(Protocol):
    """Where a constant-Q analysis places its bins and how often it reads them."""

    @property
    def analysis_rate_hz(self) -> int: ...

    @property
    def hop_length(self) -> int: ...

    @property
    def minimum_frequency_hz(self) -> float: ...

    @property
    def bins_per_octave(self) -> int: ...

    @property
    def band_count(self) -> int: ...


def constant_q_magnitude(mono: PreparedMono, *, axis: ConstantQAxis, filter_scale: float) -> NDArray[np.float64]:
    """The constant-Q magnitude of a mono along an axis, one column per hop. Shape: ``(bands, frames)``.

    `filter_scale` sets each bin's window as a share of the length its Q asks for: at 1 every bin
    spans the same number of cycles, and below 1 the low bins read a shorter stretch of the sound,
    which keeps them within a short one-shot at the cost of a wider band.
    """
    with warnings.catch_warnings():
        # librosa warns about a signal shorter than n_fft in its downsampled octaves and analyzes it regardless.
        warnings.filterwarnings("ignore", message=SHORT_SIGNAL_WARNING, category=UserWarning)
        transform = librosa.cqt(
            mono,
            sr=axis.analysis_rate_hz,
            hop_length=axis.hop_length,
            fmin=axis.minimum_frequency_hz,
            bins_per_octave=axis.bins_per_octave,
            n_bins=axis.band_count,
            filter_scale=filter_scale,
            window=CONSTANT_Q_WINDOW,
        )
    magnitude: NDArray[np.float64] = np.abs(transform)
    return magnitude


def constant_q_band_count(
    *, analysis_rate_hz: int, minimum_frequency_hz: float, bins_per_octave: int, filter_scale: float
) -> int:
    """How many constant-Q bins fit under Nyquist once each bin's window is `filter_scale` of its Q's length.

    A shorter window widens its band, and librosa keeps every band's upper reach, half the window's
    bandwidth past the bin's center, below Nyquist. This is that same reach, so the count is the
    largest librosa builds.
    """
    step = 2.0 ** (2.0 / bins_per_octave)
    relative_bandwidth = (step - 1.0) / (step + 1.0)
    reach = 1.0 + 0.5 * float(librosa.filters.window_bandwidth(CONSTANT_Q_WINDOW)) * relative_bandwidth / filter_scale
    return int(np.floor(bins_per_octave * np.log2(analysis_rate_hz / 2.0 / (minimum_frequency_hz * reach)))) + 1
