from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy.signal import find_peaks

from samplecore.waveform import average_to_fraction_points
from samplemorph.canonicalizers.common import analysis_transform
from samplemorph.geometry import LogFrequencyGeometry, log_frequency_geometry
from samplemorph.measurement.comparison import held_out_spectrum
from samplemorph.rendering import SILENT_LEVEL

FRACTION_POINT_COUNT: Final[int] = 64
ACTIVE_DEPTH_DB: Final[float] = 60.0
PEAK_PROMINENCE_DB: Final[float] = 12.0
RESOLVED_FLOOR_DB: Final[float] = 100.0
RESOLVING_GEOMETRY: Final[LogFrequencyGeometry] = log_frequency_geometry()


@dataclass(frozen=True)
class BlendFit:
    """The crossfade of two spectra that comes closest to a third, and how close it comes.

    `weight` is the share of the second spectrum in that crossfade, `residual_db` the root mean
    square the crossfade leaves unexplained, and `endpoint_distance_db` how far the two spectra
    sit apart over the same cells, which is the scale a residual is read against.
    """

    weight: float
    residual_db: float
    endpoint_distance_db: float

    @property
    def residual_share(self) -> float:
        """The residual over the endpoints' distance: near zero for a crossfade, and larger the further a point moved.

        Identical endpoints leave nothing to tell a crossfade from, so the share is zero there.
        """
        return self.residual_db / self.endpoint_distance_db if self.endpoint_distance_db > 0.0 else 0.0


def fraction_spectrum(waveform: NDArray[np.float64]) -> NDArray[np.float64]:
    """A waveform's held-out spectrum averaged onto duration-fraction columns, shaped ``(bins, FRACTION_POINT_COUNT)``.

    Two sounds of different lengths then meet column by column at the same share of their lengths,
    which is where a crossfade reads each of them.
    """
    return average_to_fraction_points(held_out_spectrum(waveform), point_count=FRACTION_POINT_COUNT, axis=1)


def blend_fit(point: NDArray[np.float64], *, first: NDArray[np.float64], second: NDArray[np.float64]) -> BlendFit:
    """Fit `point` as a decibel crossfade of `first` and `second`, over the cells any of the three sounds in.

    The least-squares share has a closed form, held inside ``[0, 1]``; the cells read are those
    within `ACTIVE_DEPTH_DB` of some spectrum's own loudest cell, which is what a listener hears.
    """
    active = _active_cells(point) | _active_cells(first) | _active_cells(second)
    difference = (second - first)[active]
    offset = (point - first)[active]
    spread = float((difference**2).sum())
    weight = float(np.clip((offset * difference).sum() / spread, 0.0, 1.0)) if spread > 0.0 else 0.0
    return BlendFit(
        weight=weight,
        residual_db=float(np.sqrt(np.mean((offset - weight * difference) ** 2))),
        endpoint_distance_db=float(np.sqrt(np.mean(difference**2))),
    )


def resolved_spectrum(waveform: NDArray[np.float64]) -> NDArray[np.float64]:
    """A waveform's power under a Gaussian analysis, averaged onto duration-fraction columns, in decibels under its peak.

    Shaped ``(bins, FRACTION_POINT_COUNT)``. The Gaussian taper keeps each partial one smooth lobe,
    and averaging power before the logarithm keeps a steady partial one peak however many frames it
    spans, so every peak counted is a partial or a resonance.
    """
    power = np.abs(analysis_transform(waveform, geometry=RESOLVING_GEOMETRY)).astype(np.float64) ** 2
    averaged = average_to_fraction_points(power, point_count=FRACTION_POINT_COUNT, axis=1)
    peak = max(float(averaged.max()), SILENT_LEVEL)
    decibels: NDArray[np.float64] = 10.0 * np.log10(
        np.maximum(averaged, peak * 10.0 ** (-RESOLVED_FLOOR_DB / 10.0)) / peak
    )
    return decibels


def mean_peak_count(spectrum: NDArray[np.float64]) -> float:
    """How many peaks at least `PEAK_PROMINENCE_DB` prominent a heard column of a resolved spectrum holds, on average.

    Two sounds heard at once carry the peaks of both, so a dissolve reads about as many as its two
    ends together, and a sound between them about as many as either.
    """
    return float(np.mean([find_peaks(column, prominence=PEAK_PROMINENCE_DB)[0].size for column in _heard(spectrum)]))


def mean_spectral_entropy(spectrum: NDArray[np.float64]) -> float:
    """How widely a heard column of a resolved spectrum spreads its power over the bins, as the mean entropy in nats."""
    power = 10.0 ** (_heard(spectrum) / 10.0)
    shares = power / power.sum(axis=1, keepdims=True)
    return float(np.mean(-(shares * np.log(shares)).sum(axis=1)))


def crest_factor_db(waveform: NDArray[np.float64]) -> float:
    """The peak over the root mean square, in decibels."""
    root_mean_square = max(float(np.sqrt(np.mean(waveform**2))), SILENT_LEVEL)
    return 20.0 * float(np.log10(max(float(np.abs(waveform).max()), SILENT_LEVEL) / root_mean_square))


def _active_cells(spectrum: NDArray[np.float64]) -> NDArray[np.bool_]:
    active: NDArray[np.bool_] = spectrum >= float(spectrum.max()) - ACTIVE_DEPTH_DB
    return active


def _heard(spectrum: NDArray[np.float64]) -> NDArray[np.float64]:
    """The columns whose loudest bin lies within `ACTIVE_DEPTH_DB` of the loudest, shaped ``(columns, bins)``."""
    columns = spectrum.T
    heard: NDArray[np.float64] = columns[columns.max(axis=1) >= float(spectrum.max()) - ACTIVE_DEPTH_DB]
    return heard
