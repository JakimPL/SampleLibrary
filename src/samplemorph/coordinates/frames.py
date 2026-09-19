from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, Field

from samplecore.models.base import FROZEN
from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.canonicalizers.common import PreparedMono
from samplemorph.canonicalizers.constant_q import constant_q_band_count, constant_q_magnitude
from samplemorph.geometry import (
    DEFAULT_CONSTANT_Q_BINS_PER_OCTAVE,
    DEFAULT_HOP_LENGTH,
    MINIMUM_FREQUENCY_HZ,
    SEMITONES_PER_OCTAVE,
)

# Half the length each bin's Q asks for keeps the lowest bins within a 0.7-second one-shot, the
# library's median, while three bins per semitone still resolve every semitone above the lowest octave.
FRAME_FILTER_SCALE: Final[float] = 0.5
DEFAULT_KEPT_FRAME_COUNT: Final[int] = 16
DEFAULT_SOUNDING_RANGE_DB: Final[float] = 30.0
DEFAULT_FRAME_RANGE_DB: Final[float] = 60.0
# 8-bit material carries its quantization noise about 48 dB under full scale, so a frame is read
# no deeper than this under the sample's loudest bin, which keeps that noise out of the quiet frames.
DEFAULT_SAMPLE_RANGE_DB: Final[float] = 70.0
SILENT_MAGNITUDE: Final[float] = 1e-12


class FrameAnalysis(BaseModel):
    """How a sound is read as constant-Q frames: the axis, the frames kept, and how deep each is read.

    A frame is one column of the constant-Q magnitude. Each keeps `frame_range_db` under its own
    loudest bin on one fixed scale, and every bin quieter than `sample_range_db` under the sample's
    loudest bin reads as silence. Up to `kept_frame_count` frames are kept, evenly spaced over the
    frames that sound within `sounding_range_db` of the loudest.
    """

    model_config = FROZEN

    analysis_rate_hz: int = Field(gt=0)
    hop_length: int = Field(gt=0)
    minimum_frequency_hz: float = Field(gt=0.0)
    bins_per_octave: int = Field(gt=0)
    band_count: int = Field(gt=0)
    filter_scale: float = Field(gt=0.0, le=1.0)
    kept_frame_count: int = Field(gt=0)
    sounding_range_db: float = Field(gt=0.0)
    frame_range_db: float = Field(gt=0.0)
    sample_range_db: float = Field(gt=0.0)

    @property
    def bins_per_semitone(self) -> float:
        return self.bins_per_octave / SEMITONES_PER_OCTAVE

    def band_frequencies_hz(self) -> NDArray[np.float64]:
        """Every bin's center frequency, lowest first."""
        bands = np.arange(self.band_count, dtype=np.float64)
        frequencies: NDArray[np.float64] = self.minimum_frequency_hz * 2.0 ** (bands / self.bins_per_octave)
        return frequencies


def frame_analysis() -> FrameAnalysis:
    """The frame analysis a pitch head reads: three constant-Q bins per semitone, as high as their windows fit."""
    return FrameAnalysis(
        analysis_rate_hz=NOMINAL_WAV_RATE,
        hop_length=DEFAULT_HOP_LENGTH,
        minimum_frequency_hz=MINIMUM_FREQUENCY_HZ,
        bins_per_octave=DEFAULT_CONSTANT_Q_BINS_PER_OCTAVE,
        band_count=constant_q_band_count(
            analysis_rate_hz=NOMINAL_WAV_RATE,
            minimum_frequency_hz=MINIMUM_FREQUENCY_HZ,
            bins_per_octave=DEFAULT_CONSTANT_Q_BINS_PER_OCTAVE,
            filter_scale=FRAME_FILTER_SCALE,
        ),
        filter_scale=FRAME_FILTER_SCALE,
        kept_frame_count=DEFAULT_KEPT_FRAME_COUNT,
        sounding_range_db=DEFAULT_SOUNDING_RANGE_DB,
        frame_range_db=DEFAULT_FRAME_RANGE_DB,
        sample_range_db=DEFAULT_SAMPLE_RANGE_DB,
    )


def constant_q_frames(mono: PreparedMono, *, analysis: FrameAnalysis) -> NDArray[np.float32]:
    """A sound's kept frames, each in [0, 1] over its own floor. Shape: ``(frames, bands)``.

    A silent sound keeps no frames, and a sound shorter than `kept_frame_count` sounding frames keeps
    every sounding frame it has.
    """
    decibels = (
        20.0
        * np.log10(
            np.maximum(constant_q_magnitude(mono, axis=analysis, filter_scale=analysis.filter_scale), SILENT_MAGNITUDE)
        ).T
    )
    frame_peaks = decibels.max(axis=1)
    sample_peak = float(frame_peaks.max())
    if sample_peak <= 20.0 * np.log10(SILENT_MAGNITUDE):
        return np.zeros((0, analysis.band_count), dtype=np.float32)
    kept = decibels[_kept_positions(frame_peaks, analysis=analysis)]
    scaled = (kept - kept.max(axis=1, keepdims=True) + analysis.frame_range_db) / analysis.frame_range_db
    scaled[kept < sample_peak - analysis.sample_range_db] = 0.0
    return np.clip(scaled, 0.0, 1.0).astype(np.float32)


def _kept_positions(frame_peaks: NDArray[np.float64], *, analysis: FrameAnalysis) -> NDArray[np.intp]:
    """Up to `kept_frame_count` frame positions, evenly spaced over the frames that sound."""
    sounding = np.flatnonzero(frame_peaks >= frame_peaks.max() - analysis.sounding_range_db)
    picks = np.round(np.linspace(0, sounding.size - 1, min(analysis.kept_frame_count, sounding.size))).astype(np.intp)
    positions: NDArray[np.intp] = sounding[np.unique(picks)]
    return positions
