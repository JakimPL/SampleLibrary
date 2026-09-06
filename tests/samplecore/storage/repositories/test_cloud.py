from __future__ import annotations

from datetime import UTC, datetime

import duckdb

from samplecore.models.cloud import ModuleCloudCoordinate, SampleCloudCoordinate
from samplecore.models.module import Module
from samplecore.models.sample import Sample
from samplecore.storage.repositories.cloud import DuckDBCloudCoordinateRepository, DuckDBModuleCloudCoordinateRepository


def _coordinate(sample_hash: str, *, x: float = 1.0, y: float = 2.0) -> SampleCloudCoordinate:
    return SampleCloudCoordinate(sample_hash=sample_hash, x=x, y=y, computed_at=datetime.now(UTC))


def _module_coordinate(module_hash: str, *, x: float = 1.0, y: float = 2.0) -> ModuleCloudCoordinate:
    return ModuleCloudCoordinate(module_hash=module_hash, x=x, y=y, computed_at=datetime.now(UTC))


def test_list_all_on_an_empty_table_returns_nothing(connection: duckdb.DuckDBPyConnection) -> None:
    assert DuckDBCloudCoordinateRepository(connection).list_all() == ()


def test_a_coordinate_round_trips_through_list_all(
    connection: duckdb.DuckDBPyConnection, stored_sample: Sample
) -> None:
    repository = DuckDBCloudCoordinateRepository(connection)
    coordinate = _coordinate(stored_sample.hash)

    repository.upsert(coordinate)

    assert repository.list_all() == (coordinate,)


def test_upserting_the_same_sample_again_replaces_its_coordinate(
    connection: duckdb.DuckDBPyConnection, stored_sample: Sample
) -> None:
    repository = DuckDBCloudCoordinateRepository(connection)
    repository.upsert(_coordinate(stored_sample.hash, x=1.0, y=2.0))
    refined = _coordinate(stored_sample.hash, x=3.0, y=4.0)

    repository.upsert(refined)

    assert repository.list_all() == (refined,)


def test_list_all_returns_one_coordinate_per_sample(
    connection: duckdb.DuckDBPyConnection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    repository = DuckDBCloudCoordinateRepository(connection)
    first = _coordinate(stored_sample.hash)
    second = _coordinate(stored_sample_b.hash)

    repository.upsert(first)
    repository.upsert(second)

    assert set(repository.list_all()) == {first, second}


def test_module_list_all_on_an_empty_table_returns_nothing(connection: duckdb.DuckDBPyConnection) -> None:
    assert DuckDBModuleCloudCoordinateRepository(connection).list_all() == ()


def test_a_module_coordinate_round_trips_through_list_all(
    connection: duckdb.DuckDBPyConnection, stored_module: Module
) -> None:
    repository = DuckDBModuleCloudCoordinateRepository(connection)
    coordinate = _module_coordinate(stored_module.hash)

    repository.upsert(coordinate)

    assert repository.list_all() == (coordinate,)


def test_upserting_the_same_module_again_replaces_its_coordinate(
    connection: duckdb.DuckDBPyConnection, stored_module: Module
) -> None:
    repository = DuckDBModuleCloudCoordinateRepository(connection)
    repository.upsert(_module_coordinate(stored_module.hash, x=1.0, y=2.0))
    refined = _module_coordinate(stored_module.hash, x=3.0, y=4.0)

    repository.upsert(refined)

    assert repository.list_all() == (refined,)


def test_module_list_all_returns_one_coordinate_per_module(
    connection: duckdb.DuckDBPyConnection, stored_module: Module, stored_module_b: Module
) -> None:
    repository = DuckDBModuleCloudCoordinateRepository(connection)
    first = _module_coordinate(stored_module.hash)
    second = _module_coordinate(stored_module_b.hash)

    repository.upsert(first)
    repository.upsert(second)

    assert set(repository.list_all()) == {first, second}


def test_replace_all_replaces_whatever_was_persisted_before(
    connection: duckdb.DuckDBPyConnection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    repository = DuckDBCloudCoordinateRepository(connection)
    repository.upsert(_coordinate(stored_sample.hash))
    replacement = _coordinate(stored_sample_b.hash)

    repository.replace_all([replacement])

    assert repository.list_all() == (replacement,)


def test_replace_all_with_an_empty_sequence_clears_the_table(
    connection: duckdb.DuckDBPyConnection, stored_sample: Sample
) -> None:
    repository = DuckDBCloudCoordinateRepository(connection)
    repository.upsert(_coordinate(stored_sample.hash))

    repository.replace_all([])

    assert repository.list_all() == ()


def test_module_replace_all_replaces_whatever_was_persisted_before(
    connection: duckdb.DuckDBPyConnection, stored_module: Module, stored_module_b: Module
) -> None:
    repository = DuckDBModuleCloudCoordinateRepository(connection)
    repository.upsert(_module_coordinate(stored_module.hash))
    replacement = _module_coordinate(stored_module_b.hash)

    repository.replace_all([replacement])

    assert repository.list_all() == (replacement,)


def test_module_replace_all_with_an_empty_sequence_clears_the_table(
    connection: duckdb.DuckDBPyConnection, stored_module: Module
) -> None:
    repository = DuckDBModuleCloudCoordinateRepository(connection)
    repository.upsert(_module_coordinate(stored_module.hash))

    repository.replace_all([])

    assert repository.list_all() == ()
