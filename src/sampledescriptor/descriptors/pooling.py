from __future__ import annotations

from math import ceil
from typing import Final

import numpy as np
from numpy.typing import NDArray

from sampledescriptor.geometry import GridGeometry
from sampledescriptor.images import Conditioners
from samplemorph.geometry import SEMITONES_PER_OCTAVE

DESCRIPTOR_BANDS_PER_SEMITONE: Final[int] = 1


def pooled_band_count(geometry: GridGeometry, *, bands_per_semitone: int) -> int:
    """How many rows a grid keeps once its bands are averaged down to `bands_per_semitone`.

    Raises:
        ValueError: the grid is coarser than the pooling asks for, so there is nothing to average.
    """
    factor = geometry.bands_per_semitone / bands_per_semitone
    if factor < 1.0:
        raise ValueError(
            f"a grid with {geometry.bands_per_semitone:.2f} bands per semitone cannot be pooled to {bands_per_semitone}"
        )
    return ceil(geometry.grid_shape[0] / factor)


def pool_bands(grid: NDArray[np.floating], *, band_count: int) -> NDArray[np.float32]:
    """Average the band axis down to `band_count` rows, each row the mean of the span it covers.

    Spans are laid out the way adaptive average pooling lays them out, so a grid pooled here for
    training and one pooled here at inference agree exactly. A descriptor reads the shape of a
    spectrum rather than its fine structure, and a coarser axis is what keeps it small and quick.
    """
    rows = grid.shape[0]
    if band_count == rows:
        return grid.astype(np.float32)
    starts = (np.arange(band_count) * rows) // band_count
    ends = -((-(np.arange(1, band_count + 1) * rows)) // band_count)
    pooled = np.stack([grid[start:end].mean(axis=0) for start, end in zip(starts, ends, strict=True)])
    return pooled.astype(np.float32)


def canonical_duration(conditioners: Conditioners) -> float:
    """How long the sound is once its retuning is set aside, in octaves of a second.

    Reading a waveform faster raises its translation and shortens its duration by the same amount,
    so their sum stays put under a retuning and moves only when the sound itself is longer or
    shorter -- which is the part a descriptor should hear.
    """
    return conditioners.log_duration + conditioners.translation_semitones / SEMITONES_PER_OCTAVE
