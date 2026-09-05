from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.module import Module
from samplecore.models.sample import Sample
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.database import connect
from samplecore.storage.repositories.module import DuckDBModuleRepository
from samplecore.storage.repositories.sample import DuckDBSampleRepository


@pytest.fixture
def connection() -> Iterator[Connection]:
    open_connection = connect(Path(":memory:"))
    yield open_connection
    open_connection.close()


@pytest.fixture
def stored_sample(connection: Connection, sample_hash_a: str) -> Sample:
    sample = Sample(hash=sample_hash_a, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
    DuckDBSampleRepository(connection).upsert(sample)
    connection.commit()
    return sample


@pytest.fixture
def stored_sample_b(connection: Connection, sample_hash_b: str) -> Sample:
    sample = Sample(hash=sample_hash_b, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
    DuckDBSampleRepository(connection).upsert(sample)
    connection.commit()
    return sample


@pytest.fixture
def stored_module(connection: Connection, module_hash_a: str) -> Module:
    repository = DuckDBModuleRepository(connection)
    module = Module(
        hash=module_hash_a,
        id=repository.next_id(),
        filename="song.it",
        tracker=TrackerFormat.IT,
        title="untitled",
        channel_count=4,
        pattern_count=1,
        instrument_count=1,
        sample_count=1,
        file_size=1024,
        ingested_at=datetime.now(UTC),
    )
    repository.insert(module)
    connection.commit()
    return module


@pytest.fixture
def stored_module_b(connection: Connection, module_hash_b: str) -> Module:
    repository = DuckDBModuleRepository(connection)
    module = Module(
        hash=module_hash_b,
        id=repository.next_id(),
        filename="song2.it",
        tracker=TrackerFormat.IT,
        title="untitled 2",
        channel_count=4,
        pattern_count=1,
        instrument_count=1,
        sample_count=1,
        file_size=1024,
        ingested_at=datetime.now(UTC),
    )
    repository.insert(module)
    connection.commit()
    return module
