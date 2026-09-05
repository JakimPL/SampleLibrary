from __future__ import annotations

from datetime import UTC, datetime

import duckdb

from samplecloud.placeholder_modules import (
    PlaceholderEmbeddingSummary,
    generate_placeholder_coordinates,
    place_and_persist_coordinates,
)
from samplecore.models.module import Module
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.repositories.cloud import DuckDBModuleCloudCoordinateRepository
from samplecore.storage.repositories.module import DuckDBModuleRepository

MODULE_HASH_A = "a" * 64
MODULE_HASH_B = "b" * 64


def _module(module_hash: str, module_id: int) -> Module:
    return Module(
        hash=module_hash,
        id=module_id,
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


def test_a_module_places_at_the_same_point_across_repeated_calls() -> None:
    module = _module(MODULE_HASH_A, 1)
    computed_at = datetime.now(UTC)

    first_pass = generate_placeholder_coordinates((module,), computed_at=computed_at)
    second_pass = generate_placeholder_coordinates((module,), computed_at=computed_at)

    assert first_pass == second_pass


def test_distinct_modules_generally_land_at_distinct_points() -> None:
    first_module = _module(MODULE_HASH_A, 1)
    second_module = _module(MODULE_HASH_B, 2)

    first, second = generate_placeholder_coordinates((first_module, second_module), computed_at=datetime.now(UTC))

    assert (first.x, first.y) != (second.x, second.y)


def test_place_and_persist_coordinates_persists_one_coordinate_per_module(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    module_repository = DuckDBModuleRepository(connection)
    module_repository.insert(_module(MODULE_HASH_A, module_repository.next_id()))
    module_repository.insert(_module(MODULE_HASH_B, module_repository.next_id()))

    summary = place_and_persist_coordinates(connection)

    assert summary == PlaceholderEmbeddingSummary(modules_placed=2)
    assert len(DuckDBModuleCloudCoordinateRepository(connection).list_all()) == 2


def test_an_empty_catalog_is_a_no_op(connection: duckdb.DuckDBPyConnection) -> None:
    summary = place_and_persist_coordinates(connection)

    assert summary == PlaceholderEmbeddingSummary(modules_placed=0)
    assert DuckDBModuleCloudCoordinateRepository(connection).list_all() == ()


def test_a_second_run_replaces_rather_than_duplicates_coordinates(connection: duckdb.DuckDBPyConnection) -> None:
    module_repository = DuckDBModuleRepository(connection)
    module_repository.insert(_module(MODULE_HASH_A, module_repository.next_id()))

    place_and_persist_coordinates(connection)
    place_and_persist_coordinates(connection)

    assert len(DuckDBModuleCloudCoordinateRepository(connection).list_all()) == 1
