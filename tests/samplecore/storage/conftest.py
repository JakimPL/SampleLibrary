from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import duckdb
import pytest
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.module import Module
from samplecore.models.sample import Sample
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.database import create_schema
from samplecore.storage.repositories.module import DuckDBModuleRepository
from samplecore.storage.repositories.sample import DuckDBSampleRepository


@pytest.fixture
def connection() -> Iterator[duckdb.DuckDBPyConnection]:
    open_connection = duckdb.connect(":memory:")
    create_schema(open_connection)
    yield open_connection
    open_connection.close()


@pytest.fixture
def stored_sample(connection: duckdb.DuckDBPyConnection, sample_hash_a: str) -> Sample:
    sample = Sample(hash=sample_hash_a, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
    DuckDBSampleRepository(connection).upsert(sample)
    return sample


@pytest.fixture
def stored_sample_b(connection: duckdb.DuckDBPyConnection, sample_hash_b: str) -> Sample:
    sample = Sample(hash=sample_hash_b, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
    DuckDBSampleRepository(connection).upsert(sample)
    return sample


@pytest.fixture
def stored_module(connection: duckdb.DuckDBPyConnection, module_hash_a: str) -> Module:
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
    return module
