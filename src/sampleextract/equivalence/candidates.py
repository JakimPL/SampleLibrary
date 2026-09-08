from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import sqrt
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import cKDTree

from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample

MINIMUM_FRAMES_FOR_RESAMPLE_COMPARISON: Final[int] = 64
MAX_RESAMPLE_RATIO: Final[float] = 8.0
MINIMUM_FINGERPRINT_COSINE_SIMILARITY: Final[float] = 0.95

# A generous but bounded tolerance on a trimmed silent tail's length, at a candidate-generation
# level cheap enough to run on stored frame counts alone -- 4410 frames covers up to half a second
# of trailing silence at a typical tracker sample rate. The scorer re-checks the actually-trimmed
# waveforms' lengths against a much tighter bound once it has read them.
MAX_TRAILING_TRIM_FRAMES: Final[int] = 4410


def gain_variant_candidate_pairs(samples: Sequence[Sample]) -> tuple[tuple[Sample, Sample], ...]:
    """Every pair of cataloged samples that could be the same content at a different gain, depth, or both.

    Two samples can only be related this way when they share the same channel layout and a frame
    count within MAX_TRAILING_TRIM_FRAMES of each other -- neither an amplitude change nor a depth
    conversion resamples, so only a trimmed silent tail can explain a difference in stored length.
    Sorting each channel-layout group by frame count and sweeping it lets the search stop as soon as
    a later sample's frame count leaves the tolerance, rather than comparing every pair outright.
    """
    candidate_pairs: list[tuple[Sample, Sample]] = []
    for channels in (ChannelLayout.MONO, ChannelLayout.STEREO):
        group = sorted((sample for sample in samples if sample.channels is channels), key=lambda sample: sample.frames)
        for first_index, first in enumerate(group):
            for second in group[first_index + 1 :]:
                if second.frames - first.frames > MAX_TRAILING_TRIM_FRAMES:
                    break
                candidate_pairs.append((first, second))

    return tuple(candidate_pairs)


def resampled_candidate_pairs(
    samples: Sequence[Sample], fingerprints: Mapping[str, NDArray[np.float64]]
) -> tuple[tuple[Sample, Sample], ...]:
    """Every pair of cataloged samples plausibly the same content at two different sample rates.

    A brute-force scan over every pair of samples is not viable at real library scale -- even
    after the ratio and minimum-length bounds below, a catalog of a few thousand samples still
    leaves millions of candidates, each expensive to score fully. Candidates are instead found via
    a spatial nearest-neighbor search over each sample's coarse fingerprint (fingerprint.py):
    genuinely unrelated content only very rarely lands within MINIMUM_FINGERPRINT_COSINE_SIMILARITY
    of another sample's fingerprint, so this narrows the search to a tractable set without
    meaningfully changing which pairs the full scorer in scoring.py ultimately sees. The ratio and
    minimum-frames bounds are then re-applied exactly on the search's own results, since
    fingerprint similarity alone says nothing about whether two samples' durations are actually
    compatible with a rate conversion.
    """
    candidate_pairs: list[tuple[Sample, Sample]] = []
    for channels in (ChannelLayout.MONO, ChannelLayout.STEREO):
        group = [sample for sample in samples if sample.channels is channels]
        if len(group) < 2:
            continue

        fingerprint_matrix = np.stack([fingerprints[sample.hash] for sample in group])
        tree = cKDTree(fingerprint_matrix)
        radius = sqrt(2.0 * (1.0 - MINIMUM_FINGERPRINT_COSINE_SIMILARITY))
        for first_index, second_index in tree.query_pairs(r=radius):
            first, second = group[first_index], group[second_index]
            if _is_plausible_resample_pair(first, second):
                candidate_pairs.append((first, second))

    return tuple(candidate_pairs)


def _is_plausible_resample_pair(first: Sample, second: Sample) -> bool:
    if first.frames == second.frames:
        return False

    lower, upper = min(first.frames, second.frames), max(first.frames, second.frames)
    return lower >= MINIMUM_FRAMES_FOR_RESAMPLE_COMPARISON and upper / lower <= MAX_RESAMPLE_RATIO
