from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy.ndimage import minimum_filter1d, uniform_filter1d

from samplemorph.geometry import gaussian_spread, gaussian_taper
from samplemorph.partials.peaks import lobe_spread_bins
from samplemorph.partials.settings import PartialSettings
from samplemorph.partials.tracks import PartialTracks

LOBE_REACH_DEPTH_DB: Final[float] = 80.0
LARGEST_LOBE_REACH_BINS: Final[int] = 64
DECIBELS_PER_DECADE: Final[float] = 10.0
LOBE_REACH_SPREADS: Final[float] = float(np.sqrt(LOBE_REACH_DEPTH_DB * np.log(10.0) / DECIBELS_PER_DECADE))


def residual_energy(
    energy: NDArray[np.float32], *, tracks: PartialTracks, fft_length: int, settings: PartialSettings
) -> NDArray[np.float32]:
    """What a spectral energy holds beyond the partials tracked in it: noise, attacks and unresolved clusters.

    Every partial stands in the spectrum as a lobe of a shape the analysis fixes, so what a partial
    explains, raised by `residual_margin_db` of headroom, comes off the energy it sits in, down to a
    floor read from the quietest bins around it. Energy the partials leave unexplained stays where
    it is, which keeps an attack sharper than the partials that follow it, and a sound with no
    partial to its name keeps its energy bin for bin. Shape: `energy` is ``(bins, frames)``, the
    analysis `fft_length` long that `tracks` were followed beside.
    """
    if tracks.track_count == 0:
        return energy

    margin = 10.0 ** (settings.residual_margin_db / DECIBELS_PER_DECADE)
    explained = lobe_energy(tracks, bin_count=int(energy.shape[0]), fft_length=fft_length)
    floor = _running_floor(energy, settings=settings)
    residual: NDArray[np.float32] = np.maximum(energy - margin * explained, np.minimum(energy, floor))
    return residual


def lobe_energy(tracks: PartialTracks, *, bin_count: int, fft_length: int) -> NDArray[np.float32]:
    """The energy every tracked partial stands for on an analysis `fft_length` long, bin by bin and frame by frame.

    A steady partial draws the Gaussian lobe of its own analysis, and one gliding draws the wider
    lobe its sweep spreads into over the window, holding the energy it carries. Shape: the result is
    ``(bin_count, frames)``.
    """
    bins_per_hertz = fft_length / tracks.rate_hz
    centers = tracks.frequency_hz.astype(np.float64) * bins_per_hertz
    spread = _lobe_spreads(centers, fft_length=fft_length, hop_length=tracks.hop_length)
    taper_sum = float(gaussian_taper(fft_length).sum())
    peak = (tracks.amplitude.astype(np.float64) * taper_sum / 2.0) ** 2 * (lobe_spread_bins(fft_length) / spread)
    reach = min(int(np.ceil(float(spread.max()) * LOBE_REACH_SPREADS)), LARGEST_LOBE_REACH_BINS)
    nearest = np.rint(centers).astype(np.int64)
    frames = np.broadcast_to(np.arange(tracks.frame_count), centers.shape)
    drawn = np.zeros(bin_count * tracks.frame_count, dtype=np.float64)
    for offset in range(-reach, reach + 1):
        indices = nearest + offset
        within = (indices >= 0) & (indices < bin_count) & (peak > 0.0)
        values = peak[within] * np.exp(-((indices[within] - centers[within]) ** 2) / spread[within] ** 2)
        drawn += np.bincount(
            indices[within] * tracks.frame_count + frames[within], weights=values, minlength=drawn.shape[0]
        )
    return drawn.reshape(bin_count, tracks.frame_count).astype(np.float32)


def _lobe_spreads(centers: NDArray[np.float64], *, fft_length: int, hop_length: int) -> NDArray[np.float64]:
    """How wide each partial's lobe stands, in bins, its own sweep over the window added to the analysis's own width."""
    frames_per_window = gaussian_spread(fft_length) / hop_length
    sweep = np.abs(np.gradient(centers, axis=1)) if centers.shape[1] > 1 else np.zeros_like(centers)
    spread: NDArray[np.float64] = np.sqrt(lobe_spread_bins(fft_length) ** 2 + (sweep * frames_per_window) ** 2)
    return spread


def _running_floor(energy: NDArray[np.float32], *, settings: PartialSettings) -> NDArray[np.float32]:
    """The least energy within `floor_reach_bins` of each bin, smoothed over `floor_smoothing_bins`.

    Noise reads its own quiet bins, which leaves the level a partial's neighborhood holds where the
    partial itself says nothing about it.
    """
    least = minimum_filter1d(energy, size=2 * settings.floor_reach_bins + 1, axis=0, mode="nearest")
    floor: NDArray[np.float32] = uniform_filter1d(least, size=settings.floor_smoothing_bins, axis=0, mode="nearest")
    return floor
