from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from samplemorph.canonicalizers import Canonicalizer
from samplemorph.geometry import Geometry
from samplemorph.training.pipeline_analysis import analyze_through_pipeline

PhaseBatchItem = tuple[NDArray[np.float32], NDArray[np.float32], NDArray[np.float32], int]


@dataclass(frozen=True)
class PhaseExample:
    """One magnitude a vocoder will meet, beside the phase that magnitude belongs with.

    `magnitude` is what the pipeline hands a vocoder: a sample carried through the canonical grid
    and read back onto the linear Fourier axis, smoothed by everything that grid discards.
    `cosine` and `sine` carry the source's own phase over the same frames, which is the phase that
    turns this very magnitude into the reconstruction listening already accepted.
    """

    magnitude: NDArray[np.float32]
    cosine: NDArray[np.float32]
    sine: NDArray[np.float32]
    frame_offset: int = 0


def phase_example(
    waveform: NDArray[np.float64], *, canonicalizer: Canonicalizer, geometry: Geometry
) -> PhaseExample | None:
    """Carry one waveform through the pipeline and pair the result with the phase it came from.

    A frame of the magnitude and a frame of the phase describe the same moment, so a crop of one
    matches a crop of the other. A silent waveform returns nothing, since it carries no phase to
    learn.
    """
    pair = analyze_through_pipeline(waveform, canonicalizer=canonicalizer, geometry=geometry)
    if pair is None:
        return None

    angle = np.angle(pair.analysis)
    return PhaseExample(
        magnitude=pair.magnitude.astype(np.float32),
        cosine=np.cos(angle).astype(np.float32),
        sine=np.sin(angle).astype(np.float32),
    )


def crop_to(example: PhaseExample, *, crop_frames: int, generator: np.random.Generator) -> PhaseExample:
    """Take a fixed span of frames, so examples of any length stack into one batch.

    A span shorter than the crop rests against silence for the rest of it. The loss counts each
    frame by how loud it is, so those frames carry no weight and teach the model nothing -- whereas
    repeating the sample to fill the crop would join its end to its beginning and teach a phase
    jump that no recording contains.

    The crop remembers where it started, since a phase read from partway through a recording is the
    phase from its beginning turned by that much.
    """
    frames = example.magnitude.shape[1]
    if frames >= crop_frames:
        start = int(generator.integers(0, frames - crop_frames + 1))
        window = slice(start, start + crop_frames)
        return PhaseExample(
            magnitude=example.magnitude[:, window],
            cosine=example.cosine[:, window],
            sine=example.sine[:, window],
            frame_offset=start,
        )

    padding = ((0, 0), (0, crop_frames - frames))
    return PhaseExample(
        magnitude=np.pad(example.magnitude, padding),
        cosine=np.pad(example.cosine, padding, constant_values=1.0),
        sine=np.pad(example.sine, padding),
        frame_offset=0,
    )


def crop_item(example: PhaseExample, *, crop_frames: int, generator: np.random.Generator) -> PhaseBatchItem:
    """One crop of the example laid out as the loader stacks it: magnitude, cosine, sine, frame offset."""
    cropped = crop_to(example, crop_frames=crop_frames, generator=generator)
    return cropped.magnitude, cropped.cosine, cropped.sine, cropped.frame_offset
