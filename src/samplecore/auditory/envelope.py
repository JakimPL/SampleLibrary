from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy.signal import fftconvolve

from samplecore.auditory.filterbank import GammatoneBank, analytic_subbands
from samplecore.auditory.framing import unit_sum_hann

COMPRESSION_EXPONENT: Final[float] = 1.0 / 3.0
ENVELOPE_FLOOR: Final[float] = 1e-6
MODULATION_ENVELOPE_RATE_HZ: Final[int] = 400
PERIODS_PER_KERNEL: Final[int] = 2
ROOT_HZ: Final[float] = 60.0
FLOOR_DB: Final[float] = 72.0
QUIET_LEVEL: Final[float] = 1e-12


def subband_envelopes(waveform: NDArray[np.float64], *, bank: GammatoneBank) -> NDArray[np.float64]:
    """Each channel's envelope over the waveform, the magnitude of its analytic signal."""
    envelopes: NDArray[np.float64] = np.abs(analytic_subbands(waveform, bank=bank))
    return envelopes


def compress(envelopes: NDArray[np.float64]) -> NDArray[np.float64]:
    """Read envelopes in the compressive domain a listener judges level in.

    The cube root is the specific-loudness compression of Zwicker's model, the same domain
    Daniel and Weber (1997) read roughness in, and a floor under the root keeps its slope finite
    at silence.
    """
    compressed: NDArray[np.float64] = (envelopes + ENVELOPE_FLOOR) ** COMPRESSION_EXPONENT
    return compressed


def decimation_kernel(factor: int) -> NDArray[np.float64]:
    """The averaging window `decimate` reads through before keeping every `factor`-th point.

    A unit-sum Hann of ``2 * factor + 1`` points places its first null at the rate the decimated
    series is read at, which keeps what lies above the new Nyquist frequency out of the reading.
    """
    return unit_sum_hann(2 * factor + 1)


def decimate(envelopes: NDArray[np.float64], *, factor: int) -> NDArray[np.float64]:
    """Lower an envelope series' rate by `factor`, averaging through `decimation_kernel` first."""
    kernel = decimation_kernel(factor)
    smoothed: NDArray[np.float64] = fftconvolve(envelopes, kernel[None, :], mode="same", axes=-1)
    return smoothed[..., ::factor]


def local_rms_envelope(mono: NDArray[np.float64], *, sample_rate_hz: int) -> NDArray[np.float64]:
    """A smooth, strictly positive local RMS level of a mono signal, point for point.

    The level is read under a Hann window two periods of `ROOT_HZ` long, a plausible low pitch
    that reads every sample under the same window whatever its content, so percussion and pitched
    material alike get one loudness contour separated from their spectral content -- OptiSample's
    own level extraction. A floor `FLOOR_DB` below the signal's peak sits under the root, which keeps
    the level finite and smooth through silence.
    """
    kernel = _odd_unit_sum_hann(round(PERIODS_PER_KERNEL * sample_rate_hz / ROOT_HZ))
    floor = max(10 ** (-FLOOR_DB / 20) * float(np.max(np.abs(mono))), QUIET_LEVEL)
    level: NDArray[np.float64] = np.sqrt(np.maximum(_windowed_mean(mono**2, kernel), 0.0) + floor**2)
    return level


def _odd_unit_sum_hann(span: int) -> NDArray[np.float64]:
    return unit_sum_hann(span + span % 2 + 1)


def _windowed_mean(values: NDArray[np.float64], kernel: NDArray[np.float64]) -> NDArray[np.float64]:
    # fftconvolve's own return type is not precise enough for mypy to carry through the division.
    covered = fftconvolve(np.ones_like(values), kernel, mode="same")
    weighted: NDArray[np.float64] = fftconvolve(values, kernel, mode="same") / covered
    return weighted
