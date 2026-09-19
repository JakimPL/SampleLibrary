from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.descriptors.pooling import pool_bands
from samplemorph.geometry import SEMITONES_PER_OCTAVE, Anchor, Geometry

MINIMUM_BINS_PER_SEMITONE: Final[float] = 2.0


@dataclass(frozen=True)
class PooledAxis:
    """The band axis a grid cache pools its grids onto, and which of its bands a ladder reading trusts.

    A ladder moves a sound along the band axis, so the reading keeps the bands where a move can be
    told from a crossfade. Low down, one semitone spans fewer Fourier bins than a partial's lobe is
    wide: a pooled band there averages partials the analysis never separated, and a spectrum moved
    by a few semitones reads much like the two spectra crossfaded. A Fourier analysis tells two
    partials apart once they stand about `MINIMUM_BINS_PER_SEMITONE` bins apart, which is where the
    trusted bands begin. At the top, a retuning pushes content past the Nyquist frequency or pulls
    empty bands into view, so the bands a ladder's interval reaches from the top are left out too.

    Raises:
        ValueError: the geometry aligns its grids to an anchor, which leaves a band with no one
            frequency to stand for.
    """

    geometry: Geometry
    band_count: int
    bands_per_semitone: int

    def __post_init__(self) -> None:
        if self.geometry.anchor is not Anchor.NONE:
            raise ValueError(f"a ladder reads unaligned grids, and this geometry aligns them to {self.geometry.anchor}")

    @property
    def dynamic_range_db(self) -> float:
        return self.geometry.dynamic_range_db

    @property
    def band_frequencies(self) -> NDArray[np.float64]:
        """The center of every pooled band, the geometric mean of the bands it averages."""
        log_frequencies = np.log2(self.geometry.band_frequencies)[:, None]
        centers: NDArray[np.float64] = 2.0 ** pool_bands(log_frequencies, band_count=self.band_count)[:, 0].astype(
            np.float64
        )
        return centers

    @property
    def lowest_resolved_band(self) -> int:
        """The first band where one semitone spans at least `MINIMUM_BINS_PER_SEMITONE` Fourier bins."""
        bin_spacing_hz = self.geometry.analysis_rate_hz / self.geometry.fft_length
        semitone_widths_hz = self.band_frequencies * (2.0 ** (1.0 / SEMITONES_PER_OCTAVE) - 1.0)
        resolved = np.flatnonzero(semitone_widths_hz >= MINIMUM_BINS_PER_SEMITONE * bin_spacing_hz)
        return int(resolved[0]) if resolved.size else self.band_count

    def reading_bands(self, *, interval_semitones: float) -> NDArray[np.bool_]:
        """The bands a ladder moving `interval_semitones` in all is read over."""
        top = self.band_count - ceil(interval_semitones * self.bands_per_semitone)
        bands = np.arange(self.band_count)
        reading: NDArray[np.bool_] = (bands >= self.lowest_resolved_band) & (bands < top)
        return reading
