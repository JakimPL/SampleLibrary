from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplecore.models.sample import Sample
from sampleextract.equivalence.scoring import MAX_TRIM_MISMATCH_FRAMES, MINIMUM_FRAMES_FOR_RESAMPLE_COMPARISON

MAX_RESAMPLE_RATIO: Final[float] = 8.0
MINIMUM_RESAMPLED_FINGERPRINT_SIMILARITY: Final[float] = 0.95
# A quiet sample requantized to 8 bits carries noise its 16-bit original lacks, which moves its shape
# fingerprint while the scorer still accepts the pair; the real catalog's accepted pairs reach 0.84.
MINIMUM_GAIN_FINGERPRINT_SIMILARITY: Final[float] = 0.8
NEIGHBOR_BLOCK_ROWS: Final[int] = 256


@dataclass(frozen=True)
class Fingerprints:
    """The fingerprints of samples sharing one channel layout, row by row.

    ``shapes`` holds each sample's shape fingerprint and ``rates`` its rate fingerprint (see
    fingerprint.py); ``trimmed_frames`` holds each sample's length once its trailing silence is
    trimmed, the length the scorers compare.
    """

    samples: tuple[Sample, ...]
    shapes: NDArray[np.float32]
    rates: NDArray[np.float32]
    trimmed_frames: NDArray[np.int64]


@dataclass(frozen=True)
class CandidateBlock:
    """The candidate pairs whose first sample falls in one block of rows."""

    gain_pairs: tuple[tuple[Sample, Sample], ...]
    resampled_pairs: tuple[tuple[Sample, Sample], ...]


def candidate_blocks(fingerprints: Fingerprints, *, block_rows: int) -> Iterator[CandidateBlock]:
    """Every pair of samples a scorer should see, found through their fingerprints a block of rows at a time.

    Two samples related by gain or depth alone share a length and a shape, so their shape
    fingerprints lie close together; two related by a resample hold the same cycles over lengths in
    proportion, so their rate fingerprints do. The cosine similarity of each block of rows against
    every later row finds those neighbors exactly, while holding one block's similarities in memory,
    so a catalog of a hundred thousand samples is searched in bounded memory and scored block by block.

    A pair whose trimmed lengths agree within ``MAX_TRIM_MISMATCH_FRAMES`` and whose shapes pass
    ``MINIMUM_GAIN_FINGERPRINT_SIMILARITY`` is a gain candidate. A pair whose lengths differ by more,
    within ``MAX_RESAMPLE_RATIO`` and past the resample comparison's frame floor, and whose rate
    fingerprints pass ``MINIMUM_RESAMPLED_FINGERPRINT_SIMILARITY`` is a resampled candidate.
    """
    row_count = fingerprints.shapes.shape[0]
    frames = fingerprints.trimmed_frames.astype(np.int32)
    for block_start in range(0, row_count, block_rows):
        block_stop = min(block_start + block_rows, row_count)
        # (block rows, rows from the block's start onward)
        shape_similarities = fingerprints.shapes[block_start:block_stop] @ fingerprints.shapes[block_start:].T
        rate_similarities = fingerprints.rates[block_start:block_stop] @ fingerprints.rates[block_start:].T
        firsts = np.arange(block_start, block_stop)[:, np.newaxis]
        seconds = np.arange(block_start, row_count)[np.newaxis, :]
        shorter = np.minimum(frames[firsts], frames[seconds])
        longer = np.maximum(frames[firsts], frames[seconds])
        after = seconds > firsts
        lengths_agree = (longer - shorter) <= MAX_TRIM_MISMATCH_FRAMES
        gain = after & lengths_agree & (shape_similarities >= MINIMUM_GAIN_FINGERPRINT_SIMILARITY)
        resampled = (
            after
            & ~lengths_agree
            & (shorter >= MINIMUM_FRAMES_FOR_RESAMPLE_COMPARISON)
            & (longer <= shorter * MAX_RESAMPLE_RATIO)
            & (rate_similarities >= MINIMUM_RESAMPLED_FINGERPRINT_SIMILARITY)
        )
        yield CandidateBlock(
            gain_pairs=_pairs(fingerprints.samples, gain, block_start=block_start),
            resampled_pairs=_pairs(fingerprints.samples, resampled, block_start=block_start),
        )


def _pairs(
    samples: tuple[Sample, ...], chosen: NDArray[np.bool_], *, block_start: int
) -> tuple[tuple[Sample, Sample], ...]:
    block_positions, later_positions = np.nonzero(chosen)
    return tuple(
        (samples[block_start + first], samples[block_start + second])
        for first, second in zip(block_positions.tolist(), later_positions.tolist())
    )
