from __future__ import annotations

from functools import cache
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplecore.waveform import average_to_fraction_points, triangular_weights
from sampledescriptor.geometry import DEFAULT_ANCHOR, Anchor, GridGeometry, grid_geometry
from sampledescriptor.images import Conditioners, SoundImage
from samplemorph.canonicalizers.common import PreparedMono, analysis_transform, harmonic_sum, to_magnitudes

GAIN_FLOOR: Final[float] = 2.0**-40
MAGNITUDE_FLOOR_RATIO: Final[float] = 1e-10


class LogFrequencyCanonicalizer:
    """Canonicalizes onto an exactly logarithmic reading of the short-time Fourier magnitude.

    Each band averages the linear Fourier bins across its own width, so a rate change is a
    whole-band translation of the picture.
    """

    def __init__(self, geometry: GridGeometry) -> None:
        self._geometry = geometry

    @property
    def geometry(self) -> GridGeometry:
        return self._geometry

    def canonicalize(self, mono: PreparedMono) -> SoundImage:
        linear = np.abs(analysis_transform(mono, geometry=self._geometry))
        bands: NDArray[np.float64] = band_weights(self._geometry) @ linear
        return to_sound_image(bands, geometry=self._geometry, frame_count=mono.shape[0])


@cache
def band_weights(geometry: GridGeometry) -> NDArray[np.float64]:
    """Weights averaging the linear Fourier bins each logarithmic band covers.

    A band spans one Fourier bin at around 560 Hz and widens with frequency from there, reaching
    about forty bins at the top of the range. Each band therefore takes a weighted mean over its
    own width, which carries every bin it covers into the picture and holds each frame's content
    where the analysis found it.

    Bands narrower than one bin widen to that much, so every band draws on the grid it is read
    from. Weights fall linearly from each band's center to its edge and sum to one per band. They
    are computed once per geometry and shared read-only.
    """
    band_frequencies = geometry.band_frequencies
    step = 2.0 ** (1.0 / geometry.bins_per_octave)
    bin_spacing = geometry.analysis_rate_hz / geometry.fft_length
    weights = triangular_weights(
        source_positions=geometry.linear_frequencies,
        target_positions=band_frequencies,
        half_widths=np.maximum(band_frequencies * (step - 1.0 / step) / 2.0, bin_spacing),
    )
    weights.setflags(write=False)
    return weights


def build_log_frequency_canonicalizer(*, anchor: Anchor = DEFAULT_ANCHOR) -> LogFrequencyCanonicalizer:
    return LogFrequencyCanonicalizer(grid_geometry(anchor=anchor))


def to_normalized_decibels(
    columns: NDArray[np.float64], *, dynamic_range_db: float
) -> tuple[NDArray[np.float64], float]:
    """Scale a magnitude grid into ``[0, 1]`` and report the gain that scaling removed.

    The peak becomes 1.0 and everything `dynamic_range_db` below it becomes 0.0, so a sample stored
    at any level produces the same picture and its level survives as `log_gain`. Returning the two
    together keeps the pair that reconstructs the original magnitudes in one place.
    """
    peak = float(columns.max())
    log_gain = float(np.log2(max(peak, GAIN_FLOOR)))
    floor = max(peak, GAIN_FLOOR) * MAGNITUDE_FLOOR_RATIO
    decibels = 20.0 * np.log10(np.maximum(columns, floor) / max(peak, GAIN_FLOOR))
    return np.clip(decibels, -dynamic_range_db, 0.0) / dynamic_range_db + 1.0, log_gain


def dominant_band(grid: NDArray[np.float64]) -> int:
    """The band carrying the most energy once the grid is averaged over time.

    A rate change translates the whole picture along the frequency axis, so the position of its
    strongest band moves by exactly that translation. Reading the strongest band rather than an
    energy-weighted mean holds for percussion as well as for tonal material, since it asks which
    part of the spectrum is loudest rather than assuming a fundamental exists to be found.
    """
    return int(np.argmax(grid.mean(axis=1)))


def fundamental_band(grid: NDArray[np.float64], *, geometry: GridGeometry) -> int:
    """The band a sound's harmonic series is built on.

    Every band is a candidate fundamental, scored by the magnitude found at each of its first
    `HARMONIC_COUNT` multiples, the higher ones counting less by `HARMONIC_DECAY` a step. A
    harmonic sound scores highest at its fundamental even when a higher partial carries more
    energy, because that partial's own multiples miss the odd harmonics, and a sound with a weak
    fundamental still scores highest there through the partials above it. The profile is the
    grid's time average read back as linear magnitude, so a partial counts by how steadily it is
    present through the sound. Material with no harmonic series scores highest at the lowest band
    that carries its energy, which moves with a rate change exactly as a fundamental would.

    Eight harmonics at a decay of 0.84 is the subharmonic summation of Hermes (1988). Measured over
    a 400-sample draw against a time-domain pitch estimate, it places seven steady tonal samples
    in ten on their fundamental where the loudest band places under half, and lands on a harmonic
    a third as often.
    """
    profile = to_magnitudes(grid.mean(axis=1), dynamic_range_db=geometry.dynamic_range_db, log_gain=0.0)
    return int(np.argmax(harmonic_sum(profile, frequencies=geometry.band_frequencies)))


def anchor_band(grid: NDArray[np.float64], *, geometry: GridGeometry) -> int:
    """The band the geometry's anchor rule picks, which alignment moves to the reference band.

    With no rule the reference band is its own anchor, so the picture stays where it is.
    """
    match geometry.anchor:
        case Anchor.NONE:
            return geometry.reference_band
        case Anchor.LOUDEST:
            return dominant_band(grid)
        case Anchor.FUNDAMENTAL:
            return fundamental_band(grid, geometry=geometry)


def shift_bands(grid: NDArray[np.float64], bands: float) -> NDArray[np.float64]:
    """Translate a grid along its frequency axis, filling what moves into view with silence.

    A whole number of bands moves rows as they are. A fractional count interpolates between
    neighboring rows, which is what an interpolated conditioner asks for when a morph lands between
    two samples' pitches.
    """
    band_count = grid.shape[0]
    source_positions = np.arange(band_count, dtype=np.float64) - bands
    lower = np.floor(source_positions).astype(int)
    weights = (source_positions - lower)[:, None]
    lower_rows = _rows_at(grid, lower)
    upper_rows = _rows_at(grid, lower + 1)
    shifted: NDArray[np.float64] = lower_rows * (1.0 - weights) + upper_rows * weights
    return shifted


def _rows_at(grid: NDArray[np.float64], indices: NDArray[np.intp]) -> NDArray[np.float64]:
    """Rows of `grid` at `indices`, reading positions beyond either edge as silence."""
    band_count = grid.shape[0]
    within_range = (indices >= 0) & (indices < band_count)
    rows = grid[np.clip(indices, 0, band_count - 1)]
    return np.where(within_range[:, None], rows, 0.0)


def align_and_describe(
    columns: NDArray[np.float64], *, geometry: GridGeometry, frame_count: int
) -> tuple[NDArray[np.float64], Conditioners]:
    """Normalize a magnitude grid into a sound image's grid and the conditioners it removed.

    The grid is scaled into ``[0, 1]`` and laid inside the geometry's shift headroom; under an
    anchoring rule it is then translated so its anchor band sits at the geometry's reference band,
    and the translation travels out as `translation_semitones`, so the picture describes timbre
    alone while the conditioners carry where that timbre sat, how long it sounded, and how loud it
    was. With no rule the picture holds every band at the frequency the analysis measured, the
    translation reads zero, and the conditioners carry the duration and the level. The headroom
    holds the largest translation the geometry allows, so the picture keeps every band the
    analysis produced.
    """
    normalized, log_gain = to_normalized_decibels(columns, dynamic_range_db=geometry.dynamic_range_db)
    headroom = geometry.shift_headroom_bands
    padded = np.pad(normalized, ((headroom, headroom), (0, 0)))
    offered_shift = float(geometry.reference_band - anchor_band(normalized, geometry=geometry))
    applied_shift = float(np.clip(round(offered_shift), -headroom, headroom))
    conditioners = Conditioners(
        translation_semitones=-applied_shift / geometry.bands_per_semitone,
        log_duration=float(np.log2(frame_count / NOMINAL_WAV_RATE)),
        log_gain=log_gain,
    )
    return shift_bands(padded, applied_shift), conditioners


def to_time_columns(magnitude: NDArray[np.float64], *, time_columns: int) -> NDArray[np.float64]:
    """Read an analysis spectrogram's frame axis onto a fixed number of duration-fraction columns.

    A column stands for a span of analysis frames, and averaging across that span carries every
    frame it covers into the picture -- which keeps a long sample's content in the time order the
    analysis found it, whatever the ratio between its frames and its columns.
    """
    return average_to_fraction_points(magnitude, point_count=time_columns, axis=1)


def to_sound_image(bands: NDArray[np.float64], *, geometry: GridGeometry, frame_count: int) -> SoundImage:
    """Assemble the canonical image from a frequency axis's own magnitude spectrogram.

    Every axis differs only in how it reads a waveform into `bands`; the time axis, the
    normalization and the alignment that follow are one shared rule, applied here.
    """
    columns = to_time_columns(bands, time_columns=geometry.time_columns)
    grid, conditioners = align_and_describe(columns, geometry=geometry, frame_count=frame_count)
    return SoundImage(grid=grid, conditioners=conditioners, geometry=geometry)
