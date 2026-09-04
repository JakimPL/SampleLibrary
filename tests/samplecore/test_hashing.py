from __future__ import annotations

import numpy as np
from trackmod.core.samples.depth import BitDepth

from samplecore.hashing import compute_module_hash, compute_sample_hash
from samplecore.models.channels import ChannelLayout

MONO = ChannelLayout.MONO
STEREO = ChannelLayout.STEREO


def _pcm(*values: float, channels: int = 1) -> np.ndarray:
    return np.array(values, dtype=np.float64).reshape(-1, channels)


def test_hashing_the_same_content_twice_gives_the_same_hash() -> None:
    pcm = _pcm(0.0, 0.5, -0.5, 0.25)

    first = compute_sample_hash(depth=BitDepth.SIXTEEN, channels=MONO, frames=4, pcm=pcm)
    second = compute_sample_hash(depth=BitDepth.SIXTEEN, channels=MONO, frames=4, pcm=pcm)

    assert first == second


def test_a_changed_sample_value_changes_the_hash() -> None:
    original = _pcm(0.0, 0.5, -0.5, 0.25)
    changed = _pcm(0.0, 0.5, -0.5, 0.26)

    original_hash = compute_sample_hash(depth=BitDepth.SIXTEEN, channels=MONO, frames=4, pcm=original)
    changed_hash = compute_sample_hash(depth=BitDepth.SIXTEEN, channels=MONO, frames=4, pcm=changed)

    assert original_hash != changed_hash


def test_mono_and_stereo_of_the_same_per_channel_content_hash_differently() -> None:
    mono = _pcm(0.0, 0.5, -0.5, 0.25, channels=1)
    stereo = _pcm(0.0, 0.0, 0.5, 0.5, -0.5, -0.5, 0.25, 0.25, channels=2)

    mono_hash = compute_sample_hash(depth=BitDepth.SIXTEEN, channels=MONO, frames=4, pcm=mono)
    stereo_hash = compute_sample_hash(depth=BitDepth.SIXTEEN, channels=STEREO, frames=4, pcm=stereo)

    assert mono_hash != stereo_hash


def test_the_same_content_at_a_different_depth_hashes_differently() -> None:
    pcm = _pcm(0.0, 0.5, -0.5, 0.25)

    eight_bit_hash = compute_sample_hash(depth=BitDepth.EIGHT, channels=MONO, frames=4, pcm=pcm)
    sixteen_bit_hash = compute_sample_hash(depth=BitDepth.SIXTEEN, channels=MONO, frames=4, pcm=pcm)

    assert eight_bit_hash != sixteen_bit_hash


def test_a_declared_frame_count_mismatch_changes_the_hash_via_domain_separation() -> None:
    pcm = _pcm(0.0, 0.5, -0.5, 0.25)

    frames_four = compute_sample_hash(depth=BitDepth.SIXTEEN, channels=MONO, frames=4, pcm=pcm)
    frames_five = compute_sample_hash(depth=BitDepth.SIXTEEN, channels=MONO, frames=5, pcm=pcm)

    assert frames_four != frames_five


def test_hashing_the_same_module_bytes_twice_gives_the_same_hash() -> None:
    data = b"a fabricated module file, its shape irrelevant to the hash"

    assert compute_module_hash(data) == compute_module_hash(data)


def test_a_changed_module_byte_changes_the_hash() -> None:
    original = b"a fabricated module file"
    changed = b"a fabricated module fila"

    assert compute_module_hash(original) != compute_module_hash(changed)
