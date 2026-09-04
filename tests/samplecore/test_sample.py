from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample


@dataclass(frozen=True)
class StoredBytesCase:
    depth: BitDepth
    channels: ChannelLayout
    frames: int
    expected_stored_bytes: int


STORED_BYTES_CASES = (
    StoredBytesCase(BitDepth.EIGHT, ChannelLayout.MONO, 10, 10),
    StoredBytesCase(BitDepth.SIXTEEN, ChannelLayout.MONO, 10, 20),
    StoredBytesCase(BitDepth.SIXTEEN, ChannelLayout.STEREO, 10, 40),
)


@pytest.mark.parametrize("case", STORED_BYTES_CASES, ids=lambda case: f"{case.depth.name}-{case.channels.name}")
def test_stored_bytes_accounts_for_depth_and_channel_count(case: StoredBytesCase, sample_hash_a: str) -> None:
    sample = Sample(hash=sample_hash_a, depth=case.depth, channels=case.channels, frames=case.frames)

    assert sample.stored_bytes == case.expected_stored_bytes


def test_a_sample_with_zero_frames_is_rejected(sample_hash_a: str) -> None:
    with pytest.raises(ValidationError):
        Sample(hash=sample_hash_a, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=0)


@pytest.mark.parametrize("invalid_hash", ["too-short", "A" * 64, "g" * 64, "a" * 63])
def test_a_malformed_hash_is_rejected(invalid_hash: str) -> None:
    with pytest.raises(ValidationError):
        Sample(hash=invalid_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)


def test_a_sample_is_immutable(mono_sample: Sample) -> None:
    with pytest.raises(ValidationError):
        mono_sample.frames = 16  # type: ignore[misc]
