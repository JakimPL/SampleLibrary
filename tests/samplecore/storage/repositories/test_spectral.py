from __future__ import annotations

from datetime import UTC, datetime

import duckdb

from samplecore.models.sample import Sample
from samplecore.models.spectral import SampleSpectralFeature
from samplecore.storage.repositories.spectral import DuckDBSampleSpectralFeatureRepository


def _feature(sample_hash: str, *, vector: tuple[float, ...] = (1.0, -2.0, 0.5)) -> SampleSpectralFeature:
    return SampleSpectralFeature(sample_hash=sample_hash, vector=vector, computed_at=datetime.now(UTC))


def test_get_on_an_unknown_hash_returns_none(connection: duckdb.DuckDBPyConnection) -> None:
    assert DuckDBSampleSpectralFeatureRepository(connection).get("f" * 64) is None


def test_list_all_on_an_empty_table_returns_nothing(connection: duckdb.DuckDBPyConnection) -> None:
    assert DuckDBSampleSpectralFeatureRepository(connection).list_all() == ()


def test_a_feature_round_trips_through_get(connection: duckdb.DuckDBPyConnection, stored_sample: Sample) -> None:
    repository = DuckDBSampleSpectralFeatureRepository(connection)
    feature = _feature(stored_sample.hash)

    repository.upsert(feature)

    assert repository.get(stored_sample.hash) == feature


def test_upserting_the_same_sample_again_replaces_its_vector(
    connection: duckdb.DuckDBPyConnection, stored_sample: Sample
) -> None:
    repository = DuckDBSampleSpectralFeatureRepository(connection)
    repository.upsert(_feature(stored_sample.hash, vector=(1.0, 2.0)))
    refined = _feature(stored_sample.hash, vector=(3.0, 4.0))

    repository.upsert(refined)

    assert repository.get(stored_sample.hash) == refined


def test_list_all_returns_one_feature_per_sample(
    connection: duckdb.DuckDBPyConnection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    repository = DuckDBSampleSpectralFeatureRepository(connection)
    first = _feature(stored_sample.hash)
    second = _feature(stored_sample_b.hash)

    repository.upsert(first)
    repository.upsert(second)

    assert set(repository.list_all()) == {first, second}


def test_replace_all_replaces_whatever_was_persisted_before(
    connection: duckdb.DuckDBPyConnection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    repository = DuckDBSampleSpectralFeatureRepository(connection)
    repository.upsert(_feature(stored_sample.hash))
    replacement = _feature(stored_sample_b.hash)

    repository.replace_all([replacement])

    assert repository.list_all() == (replacement,)


def test_replace_all_with_an_empty_sequence_clears_the_table(
    connection: duckdb.DuckDBPyConnection, stored_sample: Sample
) -> None:
    repository = DuckDBSampleSpectralFeatureRepository(connection)
    repository.upsert(_feature(stored_sample.hash))

    repository.replace_all([])

    assert repository.list_all() == ()
