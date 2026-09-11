from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.canonicalizers import Canonicalizer
from samplemorph.geometry import Geometry
from samplemorph.training.pipeline_analysis import analyze_through_pipeline
from samplemorph.vocoders.levels import peak_level
from samplemorph.vocoders.restorer_model import compress

SILENCE_DECIBELS: Final[float] = -1.0

RestorerBatchItem = tuple[NDArray[np.float32], NDArray[np.float32]]


@dataclass(frozen=True)
class RestorerExample:
    """One magnitude as the pipeline reads it back, beside the analysis it was averaged from.

    Both sides are decibels on the restorer's scale, read against the least-squares reading's own
    peak, so the target says exactly how far each bin of the real analysis sits from the smooth
    reading -- the residual the restorer learns to state.
    """

    least_squares: NDArray[np.float32]
    clean: NDArray[np.float32]

    @property
    def frame_count(self) -> int:
        return int(self.least_squares.shape[1])


def restorer_example(
    waveform: NDArray[np.float64], *, canonicalizer: Canonicalizer, geometry: Geometry
) -> RestorerExample | None:
    """Carry one waveform through the pipeline and pair the reading back with the analysis it came from.

    A silent waveform returns nothing, since it carries no structure to put back.
    """
    pair = analyze_through_pipeline(waveform, canonicalizer=canonicalizer, geometry=geometry)
    if pair is None:
        return None

    peak = peak_level(pair.magnitude)
    return RestorerExample(
        least_squares=compress(pair.magnitude, peak=peak, dynamic_range_db=geometry.dynamic_range_db),
        clean=compress(np.abs(pair.analysis), peak=peak, dynamic_range_db=geometry.dynamic_range_db),
    )


def crop_to(example: RestorerExample, *, crop_frames: int, generator: np.random.Generator) -> RestorerExample:
    """Take a fixed span of frames, so examples of any length stack into one batch.

    A span shorter than the crop rests against silence for the rest of it, on both sides alike, so
    those frames agree and teach the restorer nothing.
    """
    frames = example.frame_count
    if frames >= crop_frames:
        start = int(generator.integers(0, frames - crop_frames + 1))
        window = slice(start, start + crop_frames)
        return RestorerExample(least_squares=example.least_squares[:, window], clean=example.clean[:, window])

    padding = ((0, 0), (0, crop_frames - frames))
    return RestorerExample(
        least_squares=np.pad(example.least_squares, padding, constant_values=SILENCE_DECIBELS),
        clean=np.pad(example.clean, padding, constant_values=SILENCE_DECIBELS),
    )


def crop_item(example: RestorerExample, *, crop_frames: int, generator: np.random.Generator) -> RestorerBatchItem:
    """One crop of the example laid out as the loader stacks it: the least-squares reading, then the clean analysis."""
    cropped = crop_to(example, crop_frames=crop_frames, generator=generator)
    return cropped.least_squares, cropped.clean
