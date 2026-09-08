from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplecore.waveform import (
    average_to_fraction_points,
    fold_to_mono,
    remove_dc_offset,
    resample_to_fraction_points,
)
from samplemorph.geometry import Geometry
from samplemorph.images import AnalysisSpectrogram, Conditioners, SoundImage

GAIN_FLOOR: Final[float] = 2.0**-40
MAGNITUDE_FLOOR_RATIO: Final[float] = 1e-10


def prepare_mono(waveform: NDArray[np.float64]) -> NDArray[np.float64]:
    """Fold a stored waveform to one centered channel, the form every frequency axis analyzes."""
    return remove_dc_offset(fold_to_mono(waveform))


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


def to_magnitudes(grid: NDArray[np.float64], *, dynamic_range_db: float, log_gain: float) -> NDArray[np.float64]:
    """Undo `to_normalized_decibels`, returning the linear magnitudes a vocoder can invert."""
    decibels = (grid - 1.0) * dynamic_range_db
    magnitudes: NDArray[np.float64] = 10.0 ** (decibels / 20.0) * 2.0**log_gain
    return magnitudes


def dominant_band(grid: NDArray[np.float64]) -> int:
    """The band carrying the most energy once the grid is averaged over time.

    A rate change translates the whole picture along the frequency axis, so the position of its
    strongest band moves by exactly that translation. Reading the strongest band rather than an
    energy-weighted mean holds for percussion as well as for tonal material, since it asks which
    part of the spectrum is loudest rather than assuming a fundamental exists to be found.
    """
    return int(np.argmax(grid.mean(axis=1)))


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
    columns: NDArray[np.float64], *, geometry: Geometry, frame_count: int
) -> tuple[NDArray[np.float64], Conditioners]:
    """Normalize a magnitude grid into a sound image's grid and the conditioners it removed.

    The grid is scaled into ``[0, 1]``, laid inside the geometry's shift headroom, then translated
    so its strongest band sits at the geometry's reference band. The translation travels out as
    `translation_semitones`, so the picture describes timbre alone while the conditioners carry
    where that timbre sat, how long it sounded, and how loud it was. The headroom holds the largest
    translation the geometry allows, so the picture keeps every band the analysis produced.
    """
    normalized, log_gain = to_normalized_decibels(columns, dynamic_range_db=geometry.dynamic_range_db)
    headroom = geometry.shift_headroom_bands
    padded = np.pad(normalized, ((headroom, headroom), (0, 0)))
    offered_shift = float(geometry.reference_band - dominant_band(normalized))
    applied_shift = float(np.clip(round(offered_shift), -headroom, headroom))
    conditioners = Conditioners(
        translation_semitones=-applied_shift / geometry.bands_per_semitone,
        log_duration=float(np.log2(frame_count / NOMINAL_WAV_RATE)),
        log_gain=log_gain,
    )
    return shift_bands(padded, applied_shift), conditioners


def restore_columns(
    grid: NDArray[np.float64], *, geometry: Geometry, conditioners: Conditioners
) -> NDArray[np.float64]:
    """Undo `align_and_describe`, returning the magnitude grid the conditioners describe."""
    headroom = geometry.shift_headroom_bands
    unaligned = shift_bands(grid, conditioners.translation_semitones * geometry.bands_per_semitone)
    analyzed = unaligned[headroom : headroom + geometry.band_count]
    return to_magnitudes(analyzed, dynamic_range_db=geometry.dynamic_range_db, log_gain=conditioners.log_gain)


def frames_for_conditioners(conditioners: Conditioners, *, geometry: Geometry) -> tuple[int, int]:
    """The waveform length and analysis frame count a restored image should sound for."""
    frame_count = max(int(round(2.0**conditioners.log_duration * NOMINAL_WAV_RATE)), 1)
    analysis_frames = max(1 + frame_count // geometry.hop_length, 1)
    return frame_count, analysis_frames


def to_time_columns(magnitude: NDArray[np.float64], *, time_columns: int) -> NDArray[np.float64]:
    """Read an analysis spectrogram's frame axis onto a fixed number of duration-fraction columns.

    A column stands for a span of analysis frames, and averaging across that span carries every
    frame it covers into the picture -- which keeps a long sample's content in the time order the
    analysis found it, whatever the ratio between its frames and its columns.
    """
    return average_to_fraction_points(magnitude, point_count=time_columns, axis=1)


def to_analysis_frames(columns: NDArray[np.float64], *, frame_count: int) -> NDArray[np.float64]:
    """Read duration-fraction columns back onto `frame_count` analysis frames."""
    return resample_to_fraction_points(columns, point_count=frame_count, axis=1)


def to_sound_image(bands: NDArray[np.float64], *, geometry: Geometry, frame_count: int) -> SoundImage:
    """Assemble the canonical image from a frequency axis's own magnitude spectrogram.

    Every axis differs only in how it reads a waveform into `bands`; the time axis, the
    normalization and the alignment that follow are one shared rule, applied here.
    """
    columns = to_time_columns(bands, time_columns=geometry.time_columns)
    grid, conditioners = align_and_describe(columns, geometry=geometry, frame_count=frame_count)
    return SoundImage(grid=grid, conditioners=conditioners, geometry=geometry)


def bands_onto_linear_axis(
    magnitude: NDArray[np.float64],
    *,
    band_frequencies: NDArray[np.float64],
    linear_frequencies: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Read a magnitude spectrogram from its own bands onto the linear Fourier frequency grid.

    Every axis returns to audio through one magnitude inversion on the Fourier grid, so the reading
    that gets it there is one rule shared by all of them. Bins outside the range the bands cover
    read as silence, which carries the content the analysis measured and states nothing about the
    rest.
    """
    return np.stack(
        [np.interp(linear_frequencies, band_frequencies, frame, left=0.0, right=0.0) for frame in magnitude.T]
    ).T


def restore_spectrogram(image: SoundImage, *, geometry: Geometry) -> AnalysisSpectrogram:
    """Undo `to_sound_image`, returning the magnitude spectrogram the image describes."""
    columns = restore_columns(image.grid, geometry=geometry, conditioners=image.conditioners)
    frame_count, analysis_frames = frames_for_conditioners(image.conditioners, geometry=geometry)
    magnitude = to_analysis_frames(columns, frame_count=analysis_frames)
    return AnalysisSpectrogram(magnitude=magnitude, geometry=geometry, frame_count=frame_count)
