from __future__ import annotations

from datetime import UTC, datetime

import duckdb

from samplecore.models.module import Module
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.repositories.module import DuckDBModuleRepository


def _build_module(module_hash: str, module_id: int) -> Module:
    return Module(
        hash=module_hash,
        id=module_id,
        filename="song.xm",
        tracker=TrackerFormat.XM,
        title="a song",
        channel_count=8,
        pattern_count=32,
        instrument_count=16,
        sample_count=20,
        file_size=65536,
        ingested_at=datetime.now(UTC),
    )


def test_a_stored_module_round_trips_through_get(connection: duckdb.DuckDBPyConnection, module_hash_a: str) -> None:
    repository = DuckDBModuleRepository(connection)
    module = _build_module(module_hash_a, repository.next_id())

    repository.insert(module)

    assert repository.get(module_hash_a) == module


def test_get_on_an_unknown_hash_returns_none(connection: duckdb.DuckDBPyConnection, module_hash_a: str) -> None:
    repository = DuckDBModuleRepository(connection)

    assert repository.get(module_hash_a) is None


def test_next_id_produces_increasing_values(connection: duckdb.DuckDBPyConnection) -> None:
    repository = DuckDBModuleRepository(connection)

    first_id = repository.next_id()
    second_id = repository.next_id()

    assert second_id > first_id
