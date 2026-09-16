from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Final

import librosa
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from numpy.typing import NDArray

from samplemorph.canonicalizers.common import SHORT_SIGNAL_WARNING
from samplemorph.geometry import gaussian_spread, gaussian_taper
from samplemorph.partials.settings import PartialSettings

SILENT_MAGNITUDE: Final[float] = 1e-30
DECIBELS_PER_NEPER: Final[float] = 20.0 / np.log(10.0)


@dataclass(frozen=True)
class SpectralPeaks:
    """Every peak of a Gaussian analysis that reads as a sinusoid, in frame order.

    Each peak's frequency and amplitude come from the parabola through the logarithm of its three
    nearest bins, exact for a stationary sinusoid under a Gaussian taper, and its amplitude is the
    sinusoid's own, so a peak of amplitude 0.5 is a sinusoid peaking at 0.5. Shapes: every array is
    ``(peaks,)``.
    """

    frames: NDArray[np.intp]
    frequency_hz: NDArray[np.float64]
    amplitude: NDArray[np.float64]
    frame_count: int


def analysis_length(rate_hz: float, *, settings: PartialSettings) -> int:
    """The power of two nearest `analysis_seconds` as heard at `rate_hz`, so every rate resolves partials alike."""
    return int(2 ** round(float(np.log2(settings.analysis_seconds * rate_hz))))


def gaussian_transform(mono: NDArray[np.float64], *, window_length: int, hop_length: int) -> NDArray[np.complex128]:
    """The short-time Fourier transform under a Gaussian taper, frames centered every `hop_length` samples.

    Shape: ``(window_length // 2 + 1, 1 + samples // hop_length)``.
    """
    with warnings.catch_warnings():
        # librosa warns about a signal shorter than n_fft and analyzes it regardless.
        warnings.filterwarnings("ignore", message=SHORT_SIGNAL_WARNING, category=UserWarning)
        transform: NDArray[np.complex128] = librosa.stft(
            mono, n_fft=window_length, hop_length=hop_length, window=gaussian_taper(window_length)
        )
    return transform


def pick_peaks(
    transform: NDArray[np.complex128],
    *,
    rate_hz: float,
    window_length: int,
    settings: PartialSettings,
) -> SpectralPeaks:
    """The peaks of a Gaussian analysis that behave like sinusoids.

    A local maximum is kept when it stands within the settings' depths of its frame's loudest peak
    and of the sound's, when it rises `local_prominence_db` over the median of the bins around it, and
    when its lobe curves within the settings' range of a stationary sinusoid's. The median holds
    noise to a few decibels under its own peaks while a partial stands tens of decibels over it; the
    curvature leaves out the wide humps two partials too close to resolve make. A gliding partial
    spreads into a wider lobe of the same shape, lower by the fourth root of its curvature ratio,
    and its amplitude is read back up by that root.
    """
    log_magnitude = np.log(np.maximum(np.abs(transform), SILENT_MAGNITUDE)).astype(np.float32)
    below, center, above = log_magnitude[:-2], log_magnitude[1:-1], log_magnitude[2:]
    curvature = 0.5 * (below - 2.0 * center + above)
    slope = 0.5 * (above - below)
    is_maximum = (center > below) & (center >= above) & (curvature < 0.0)
    safe_curvature = np.where(is_maximum, curvature, -1.0)
    offset = -slope / (2.0 * safe_curvature)
    vertex = center - slope**2 / (4.0 * safe_curvature)
    curvature_ratio = -safe_curvature * (2.0 * lobe_spread_bins(window_length) ** 2)
    prominent = vertex - _local_median(log_magnitude, reach=settings.local_reach_bins)[1:-1] >= (
        settings.local_prominence_db / DECIBELS_PER_NEPER
    )
    kept = (
        is_maximum
        & prominent
        & (curvature_ratio >= settings.lowest_curvature_ratio)
        & (curvature_ratio <= settings.highest_curvature_ratio)
        & _within_depths(np.where(is_maximum, vertex, -np.inf), settings=settings)
    )
    bin_indices, frames = np.nonzero(kept)
    order = np.lexsort((bin_indices, frames))
    bin_indices, frames = bin_indices[order], frames[order]
    widening = np.minimum(curvature_ratio[bin_indices, frames].astype(np.float64), 1.0) ** -0.25
    return SpectralPeaks(
        frames=frames.astype(np.intp),
        frequency_hz=(bin_indices + 1 + offset[bin_indices, frames].astype(np.float64)) * rate_hz / window_length,
        amplitude=2.0
        * np.exp(vertex[bin_indices, frames].astype(np.float64))
        * widening
        / float(gaussian_taper(window_length).sum()),
        frame_count=int(transform.shape[1]),
    )


def lobe_spread_bins(window_length: int) -> float:
    """The standard deviation, in bins, of a sinusoid's magnitude lobe under the Gaussian taper, the same at any length."""
    return window_length / (2.0 * np.pi * gaussian_spread(window_length))


def _local_median(log_magnitude: NDArray[np.float32], *, reach: int) -> NDArray[np.float32]:
    """Each bin's median over the `reach` bins on either side in its own frame, the edges repeating their last bin."""
    padded = np.pad(log_magnitude, ((reach, reach), (0, 0)), mode="edge")
    # sliding_window_view puts the window last: (bins, frames, 2 * reach + 1)
    windows = sliding_window_view(padded, 2 * reach + 1, axis=0)
    median: NDArray[np.float32] = np.partition(windows, reach, axis=-1)[..., reach]
    return median


def _within_depths(vertex: NDArray[np.float32], *, settings: PartialSettings) -> NDArray[np.bool_]:
    """Which vertices stand within the peak depth of their frame's loudest and the sound depth of the loudest overall."""
    frame_loudest = vertex.max(axis=0, keepdims=True)
    sound_loudest = float(frame_loudest.max()) if vertex.size else -np.inf
    within: NDArray[np.bool_] = (vertex >= frame_loudest - settings.peak_depth_db / DECIBELS_PER_NEPER) & (
        vertex >= sound_loudest - settings.sound_depth_db / DECIBELS_PER_NEPER
    )
    return within
