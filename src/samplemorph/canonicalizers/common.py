from __future__ import annotations

import warnings
from typing import Final, NewType

import librosa
import numpy as np
from numpy.typing import NDArray

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplecore.waveform import (
    average_to_fraction_points,
    fold_to_mono,
    remove_subsonic,
    resample_to_fraction_points,
)
from samplemorph.geometry import Anchor, Geometry, analysis_taper
from samplemorph.images import AnalysisSpectrogram, Conditioners, SoundImage

GAIN_FLOOR: Final[float] = 2.0**-40
MAGNITUDE_FLOOR_RATIO: Final[float] = 1e-10
HARMONIC_COUNT: Final[int] = 8
HARMONIC_DECAY: Final[float] = 0.84
SHORT_SIGNAL_WARNING: Final[str] = r"n_fft=\d+ is too large for input signal"

# One channel of frames that has come in through `prepare_mono`, or a retuning of such frames.
PreparedMono = NewType("PreparedMono", NDArray[np.float64])


def prepare_mono(waveform: NDArray[np.float64]) -> PreparedMono:
    """Fold a stored waveform to the one audible channel every frequency axis analyzes.

    The band below hearing leaves here, at the pipeline's way in and nowhere else, so every
    analysis, every reconstruction and every reference a reconstruction is measured against carries
    the same content a listener does, filtered once. The filter is designed at the nominal
    container rate, which is the rate every frequency axis reads its frames at.
    """
    return PreparedMono(remove_subsonic(fold_to_mono(waveform), sample_rate_hz=NOMINAL_WAV_RATE))


def analysis_transform(mono: NDArray[np.float64], *, geometry: Geometry) -> NDArray[np.complex128]:
    """The short-time Fourier transform a prepared waveform is read through on this geometry.

    One frame per hop through the geometry's taper, centered so the first frame sits on the
    waveform's start. A hit shorter than one transform is read the same way: librosa pads half a
    transform of silence on each side before framing, so the hit fills the few frames its length
    gives it, and the length warning librosa raises on the way stays out of the logs.
    """
    with warnings.catch_warnings():
        # librosa warns about a signal shorter than n_fft and analyzes it regardless.
        warnings.filterwarnings("ignore", message=SHORT_SIGNAL_WARNING, category=UserWarning)
        transform: NDArray[np.complex128] = librosa.stft(
            mono, n_fft=geometry.fft_length, hop_length=geometry.hop_length, window=analysis_taper(geometry)
        )
    return transform


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


def fundamental_band(grid: NDArray[np.float64], *, geometry: Geometry) -> int:
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
    a third as often; `16-pitch-anchor.md` holds the table.
    """
    profile = to_magnitudes(grid.mean(axis=1), dynamic_range_db=geometry.dynamic_range_db, log_gain=0.0)
    frequencies = geometry.band_frequencies
    total = np.zeros_like(profile)
    for harmonic in range(1, HARMONIC_COUNT + 1):
        total += HARMONIC_DECAY ** (harmonic - 1) * np.interp(harmonic * frequencies, frequencies, profile, right=0.0)
    return int(np.argmax(total))


def anchor_band(grid: NDArray[np.float64], *, geometry: Geometry) -> int:
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
    columns: NDArray[np.float64], *, geometry: Geometry, frame_count: int
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
