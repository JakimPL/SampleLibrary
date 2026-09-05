from __future__ import annotations

import pytest
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample


@pytest.fixture
def sample_hash_a() -> str:
    return "a" * 64


@pytest.fixture
def sample_hash_b() -> str:
    return "b" * 64


@pytest.fixture
def module_hash_a() -> str:
    return "c" * 64


@pytest.fixture
def module_hash_b() -> str:
    return "d" * 64


@pytest.fixture
def mono_sample(sample_hash_a: str) -> Sample:
    return Sample(hash=sample_hash_a, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
