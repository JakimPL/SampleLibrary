from __future__ import annotations

import duckdb
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.storage.repositories.sample import DuckDBSampleRepository


def test_a_stored_sample_round_trips_through_get(connection: duckdb.DuckDBPyConnection, sample_hash_a: str) -> None:
    repository = DuckDBSampleRepository(connection)
    sample = Sample(hash=sample_hash_a, depth=BitDepth.EIGHT, channels=ChannelLayout.STEREO, frames=12)

    repository.upsert(sample)

    assert repository.get(sample_hash_a) == sample


def test_get_on_an_unknown_hash_returns_none(connection: duckdb.DuckDBPyConnection, sample_hash_a: str) -> None:
    repository = DuckDBSampleRepository(connection)

    assert repository.get(sample_hash_a) is None


def test_upserting_the_same_sample_twice_does_not_raise(
    connection: duckdb.DuckDBPyConnection, sample_hash_a: str
) -> None:
    repository = DuckDBSampleRepository(connection)
    sample = Sample(hash=sample_hash_a, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=4)

    repository.upsert(sample)
    repository.upsert(sample)

    assert repository.get(sample_hash_a) == sample


def test_list_all_on_an_empty_catalog_returns_nothing(connection: duckdb.DuckDBPyConnection) -> None:
    assert DuckDBSampleRepository(connection).list_all() == ()


def test_list_all_returns_every_stored_sample(
    connection: duckdb.DuckDBPyConnection, sample_hash_a: str, sample_hash_b: str
) -> None:
    repository = DuckDBSampleRepository(connection)
    first = Sample(hash=sample_hash_a, depth=BitDepth.EIGHT, channels=ChannelLayout.MONO, frames=4)
    second = Sample(hash=sample_hash_b, depth=BitDepth.SIXTEEN, channels=ChannelLayout.STEREO, frames=16)
    repository.upsert(first)
    repository.upsert(second)

    assert set(repository.list_all()) == {first, second}
