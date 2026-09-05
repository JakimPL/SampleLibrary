from __future__ import annotations

import numpy as np
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from sampleextract.equivalence.candidates import (
    MAX_RESAMPLE_RATIO,
    MINIMUM_FRAMES_FOR_RESAMPLE_COMPARISON,
    bit_depth_candidate_pairs,
    resampled_candidate_pairs,
)

_SIMILAR_FINGERPRINT_A = np.array([1.0, 0.0, 0.0, 0.0])
_SIMILAR_FINGERPRINT_B = np.array([0.99, 0.01, 0.0, 0.0])
_SIMILAR_FINGERPRINT_B = _SIMILAR_FINGERPRINT_B / np.linalg.norm(_SIMILAR_FINGERPRINT_B)
_DISSIMILAR_FINGERPRINT = np.array([0.0, 0.0, 0.0, 1.0])


def _sample(seed: int, *, depth: BitDepth, channels: ChannelLayout, frames: int) -> Sample:
    return Sample(hash=format(seed, "064x"), depth=depth, channels=channels, frames=frames)


def test_bit_depth_candidates_pairs_matching_channels_and_frames_at_different_depth() -> None:
    eight_bit = _sample(1, depth=BitDepth.EIGHT, channels=ChannelLayout.MONO, frames=100)
    sixteen_bit = _sample(2, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=100)

    assert bit_depth_candidate_pairs((eight_bit, sixteen_bit)) == ((eight_bit, sixteen_bit),)


def test_bit_depth_candidates_excludes_a_pair_with_matching_depth() -> None:
    first = _sample(1, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=100)
    second = _sample(2, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=100)

    assert bit_depth_candidate_pairs((first, second)) == ()


def test_bit_depth_candidates_excludes_a_pair_with_different_frames() -> None:
    first = _sample(1, depth=BitDepth.EIGHT, channels=ChannelLayout.MONO, frames=100)
    second = _sample(2, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=200)

    assert bit_depth_candidate_pairs((first, second)) == ()


def test_bit_depth_candidates_excludes_a_pair_with_different_channels() -> None:
    first = _sample(1, depth=BitDepth.EIGHT, channels=ChannelLayout.MONO, frames=100)
    second = _sample(2, depth=BitDepth.SIXTEEN, channels=ChannelLayout.STEREO, frames=100)

    assert bit_depth_candidate_pairs((first, second)) == ()


def test_resampled_candidates_pairs_similar_fingerprints_within_the_ratio_bound() -> None:
    short = _sample(1, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=1000)
    long_ = _sample(2, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=int(1000 * MAX_RESAMPLE_RATIO))
    fingerprints = {short.hash: _SIMILAR_FINGERPRINT_A, long_.hash: _SIMILAR_FINGERPRINT_B}

    assert resampled_candidate_pairs((short, long_), fingerprints) == ((short, long_),)


def test_resampled_candidates_excludes_a_similar_pair_beyond_the_ratio_bound() -> None:
    short = _sample(1, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=1000)
    long_ = _sample(2, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=int(1000 * MAX_RESAMPLE_RATIO) + 1)
    fingerprints = {short.hash: _SIMILAR_FINGERPRINT_A, long_.hash: _SIMILAR_FINGERPRINT_B}

    assert resampled_candidate_pairs((short, long_), fingerprints) == ()


def test_resampled_candidates_excludes_a_pair_with_dissimilar_fingerprints() -> None:
    first = _sample(1, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=1000)
    second = _sample(2, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=2000)
    fingerprints = {first.hash: _SIMILAR_FINGERPRINT_A, second.hash: _DISSIMILAR_FINGERPRINT}

    assert resampled_candidate_pairs((first, second), fingerprints) == ()


def test_resampled_candidates_excludes_a_similar_pair_with_matching_frames() -> None:
    first = _sample(1, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=1000)
    second = _sample(2, depth=BitDepth.EIGHT, channels=ChannelLayout.MONO, frames=1000)
    fingerprints = {first.hash: _SIMILAR_FINGERPRINT_A, second.hash: _SIMILAR_FINGERPRINT_B}

    assert resampled_candidate_pairs((first, second), fingerprints) == ()


def test_resampled_candidates_excludes_a_similar_pair_with_different_channels() -> None:
    first = _sample(1, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=1000)
    second = _sample(2, depth=BitDepth.SIXTEEN, channels=ChannelLayout.STEREO, frames=2000)
    fingerprints = {first.hash: _SIMILAR_FINGERPRINT_A, second.hash: _SIMILAR_FINGERPRINT_B}

    assert resampled_candidate_pairs((first, second), fingerprints) == ()


def test_resampled_candidates_excludes_a_similar_pair_below_the_minimum_frame_floor() -> None:
    short_frames = MINIMUM_FRAMES_FOR_RESAMPLE_COMPARISON - 1
    first = _sample(1, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=short_frames)
    second = _sample(2, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=short_frames * 2)
    fingerprints = {first.hash: _SIMILAR_FINGERPRINT_A, second.hash: _SIMILAR_FINGERPRINT_B}

    assert resampled_candidate_pairs((first, second), fingerprints) == ()
