from __future__ import annotations

from datetime import UTC, datetime

import duckdb

from samplecore.models.cloud import SampleCloudCoordinate
from samplecore.models.sample import Sample
from samplecore.storage.repositories.cloud import DuckDBCloudCoordinateRepository


def _coordinate(sample_hash: str, *, x: float = 1.0, y: float = 2.0) -> SampleCloudCoordinate:
    return SampleCloudCoordinate(sample_hash=sample_hash, x=x, y=y, computed_at=datetime.now(UTC))


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
