from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest
from numpy.typing import NDArray
from scipy.spatial import cKDTree
from trackmod.binary.pcm.quantize import dequantize, quantize
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.waveform import trim_trailing_silence
from sampleextract.equivalence.candidates import (
    MAX_RESAMPLE_RATIO,
    MINIMUM_GAIN_FINGERPRINT_SIMILARITY,
    MINIMUM_RESAMPLED_FINGERPRINT_SIMILARITY,
    CandidateBlock,
    Fingerprints,
    candidate_blocks,
)
from sampleextract.equivalence.fingerprint import compute_rate_fingerprint, compute_shape_fingerprint
from sampleextract.equivalence.scoring import (
    GAIN_VARIANT_MINIMUM_CONFIDENCE,
    MAX_TRIM_MISMATCH_FRAMES,
    MINIMUM_FRAMES_FOR_RESAMPLE_COMPARISON,
    TRAILING_SILENCE_THRESHOLD,
    score_gain_variant,
)

SAMPLE_RATE = 8363
SIMILAR = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
NEARLY_SIMILAR = np.array([0.9, np.sqrt(1.0 - 0.9**2), 0.0, 0.0], dtype=np.float32)
DISSIMILAR = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)


def _sample(seed: int) -> Sample:
    return Sample(hash=format(seed, "064x"), depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=100_000)


def _fingerprints(rows: list[tuple[NDArray[np.float32], int]]) -> Fingerprints:
    """Fingerprints whose shape and rate readings agree, so each case is about one threshold at a time."""
    stacked = np.stack([fingerprint for fingerprint, _ in rows])
    return Fingerprints(
        samples=tuple(_sample(seed) for seed in range(len(rows))),
        shapes=stacked,
        rates=stacked,
        trimmed_frames=np.array([frames for _, frames in rows], dtype=np.int64),
    )


def _merged(blocks: list[CandidateBlock]) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    def indices(pairs: tuple[tuple[Sample, Sample], ...]) -> set[tuple[int, int]]:
        return {(int(first.hash, 16), int(second.hash, 16)) for first, second in pairs}

    gain: set[tuple[int, int]] = set()
    resampled: set[tuple[int, int]] = set()
    for block in blocks:
        gain |= indices(block.gain_pairs)
        resampled |= indices(block.resampled_pairs)
    return gain, resampled


@pytest.mark.parametrize("block_rows", [1, 7, 500])
def test_the_block_search_finds_exactly_the_pairs_a_radius_search_finds(block_rows: int) -> None:
    rng = np.random.default_rng(5)
    centers = rng.standard_normal((12, 16))
    rows = centers[rng.integers(0, 12, 200)] + rng.standard_normal((200, 16)) * 0.15
    unit_rows = (rows / np.linalg.norm(rows, axis=1, keepdims=True)).astype(np.float32)
    fingerprints = Fingerprints(
        samples=tuple(_sample(seed) for seed in range(200)),
        shapes=unit_rows,
        rates=unit_rows,
        trimmed_frames=np.full(200, 1000, dtype=np.int64),
    )

    gain, _ = _merged(list(candidate_blocks(fingerprints, block_rows=block_rows)))

    radius = np.sqrt(2.0 * (1.0 - MINIMUM_GAIN_FINGERPRINT_SIMILARITY))
    expected = cKDTree(unit_rows.astype(np.float64)).query_pairs(r=radius - 1e-6)
    assert gain >= expected
    assert all(
        float(unit_rows[first] @ unit_rows[second]) >= MINIMUM_GAIN_FINGERPRINT_SIMILARITY - 1e-5
        for first, second in gain
    )


@dataclass(frozen=True)
class ClassificationCase:
    second_fingerprint: NDArray[np.float32]
    first_frames: int
    second_frames: int
    gain: bool
    resampled: bool


@pytest.mark.parametrize(
    "case",
    [
        ClassificationCase(SIMILAR, 1000, 1000 + MAX_TRIM_MISMATCH_FRAMES, gain=True, resampled=False),
        ClassificationCase(SIMILAR, 1000, 2000, gain=False, resampled=True),
        ClassificationCase(SIMILAR, 1000, int(1000 * MAX_RESAMPLE_RATIO) + 1, gain=False, resampled=False),
        ClassificationCase(NEARLY_SIMILAR, 1000, 2000, gain=False, resampled=False),
        ClassificationCase(NEARLY_SIMILAR, 1000, 1010, gain=True, resampled=False),
        ClassificationCase(DISSIMILAR, 1000, 1000, gain=False, resampled=False),
        ClassificationCase(
            SIMILAR,
            MINIMUM_FRAMES_FOR_RESAMPLE_COMPARISON - 1,
            (MINIMUM_FRAMES_FOR_RESAMPLE_COMPARISON - 1) * 2,
            gain=False,
            resampled=False,
        ),
    ],
    ids=(
        "a trimmed tail within tolerance",
        "a resample",
        "a ratio past the bound",
        "a stretched pair short of the resampled floor",
        "a same-length pair past the gain floor",
        "unrelated content",
        "too short to compare as a resample",
    ),
)
def test_a_close_pair_is_classified_by_how_its_trimmed_lengths_relate(case: ClassificationCase) -> None:
    assert float(NEARLY_SIMILAR @ SIMILAR) >= MINIMUM_GAIN_FINGERPRINT_SIMILARITY
    assert float(NEARLY_SIMILAR @ SIMILAR) < MINIMUM_RESAMPLED_FINGERPRINT_SIMILARITY
    fingerprints = _fingerprints([(SIMILAR, case.first_frames), (case.second_fingerprint, case.second_frames)])

    gain, resampled = _merged(list(candidate_blocks(fingerprints, block_rows=2)))

    assert (gain == {(0, 1)}) is case.gain
    assert (resampled == {(0, 1)}) is case.resampled


@dataclass(frozen=True)
class GainVariantCase:
    content: str
    level: float
    gain: float
    requantized: bool
    silent_tail: int


def _content(kind: str, frames: int) -> NDArray[np.float64]:
    time = np.arange(frames) / SAMPLE_RATE
    match kind:
        case "tonal":
            waveform = np.sin(2 * np.pi * 440 * time) + 0.4 * np.sin(2 * np.pi * 1320 * time)
        case "noise":
            waveform = np.random.default_rng(9).standard_normal(frames)
        case _:
            waveform = np.sin(2 * np.pi * 220 * time) * np.exp(-time * 8)
    return (waveform / np.abs(waveform).max()).reshape(-1, 1)


@pytest.mark.parametrize(
    "case",
    [
        GainVariantCase(content, level, gain, requantized, silent_tail)
        for content in ("tonal", "noise", "decay")
        for level in (0.5, 0.03)
        for gain in (1.0, 0.5, 0.1)
        for requantized in (False, True)
        for silent_tail in (0, 20, 4410)
    ],
)
def test_every_accepted_gain_variant_is_a_gain_candidate(case: GainVariantCase) -> None:
    """A pair the gain scorer accepts is one the fingerprint search puts in front of it."""
    original = dequantize(quantize(_content(case.content, 3000) * case.level, BitDepth.SIXTEEN), BitDepth.SIXTEEN)
    variant = original * case.gain
    depth = BitDepth.SIXTEEN
    if case.requantized:
        variant = dequantize(quantize(variant, BitDepth.EIGHT), BitDepth.EIGHT)
        depth = BitDepth.EIGHT
    variant = np.pad(variant, ((0, case.silent_tail), (0, 0)))
    first = trim_trailing_silence(original, threshold=TRAILING_SILENCE_THRESHOLD)
    second = trim_trailing_silence(variant, threshold=TRAILING_SILENCE_THRESHOLD)
    score = score_gain_variant(first, second, depth_a=BitDepth.SIXTEEN, depth_b=depth)
    if second.shape[0] == 0 or score is None or score.confidence < GAIN_VARIANT_MINIMUM_CONFIDENCE:
        pytest.skip("the scorer itself refuses this pair")
    fingerprints = Fingerprints(
        samples=(_sample(0), _sample(1)),
        shapes=np.stack([compute_shape_fingerprint(first), compute_shape_fingerprint(second)]).astype(np.float32),
        rates=np.stack([compute_rate_fingerprint(first), compute_rate_fingerprint(second)]).astype(np.float32),
        trimmed_frames=np.array([first.shape[0], second.shape[0]], dtype=np.int64),
    )

    gain, _ = _merged(list(candidate_blocks(fingerprints, block_rows=2)))

    assert gain == {(0, 1)}
