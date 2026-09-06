from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pytest
from trackmod.core.samples.depth import BitDepth

from samplecloud.feature_store import write_features
from samplecloud.reduce import CloudSummary, reduce_and_persist_coordinates
from samplecore.models.channels import ChannelLayout
from samplecore.models.cloud import SampleCloudCoordinate
from samplecore.models.sample import Sample
from samplecore.storage.repositories.cloud import DuckDBCloudCoordinateRepository
from samplecore.storage.repositories.sample import DuckDBSampleRepository
from samplecore.storage.repositories.spectral import DuckDBSampleSpectralFeatureRepository

FEATURE_VECTOR_COUNT = 6
FEATURE_DIMENSIONS = 4


def _seed_samples_and_features(connection: duckdb.DuckDBPyConnection, tmp_path: Path) -> Path:
    repository = DuckDBSampleRepository(connection)
    features = {}
    for seed in range(FEATURE_VECTOR_COUNT):
        sample_hash = format(seed + 1, "064x")
        repository.upsert(Sample(hash=sample_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=32))
        features[sample_hash] = np.random.default_rng(seed).uniform(-1.0, 1.0, FEATURE_DIMENSIONS)

    store_path = tmp_path / "features.parquet"
    write_features(store_path, features)
    return store_path


def test_reduce_persists_one_coordinate_per_feature_vector(
    connection: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    store_path = _seed_samples_and_features(connection, tmp_path)

    summary = reduce_and_persist_coordinates(connection, store_path)

    assert summary == CloudSummary(samples_reduced=FEATURE_VECTOR_COUNT)
    assert len(DuckDBCloudCoordinateRepository(connection).list_all()) == FEATURE_VECTOR_COUNT


def test_reduce_also_persists_a_standardized_feature_vector_per_sample(
    connection: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    store_path = _seed_samples_and_features(connection, tmp_path)

    reduce_and_persist_coordinates(connection, store_path)

    features = DuckDBSampleSpectralFeatureRepository(connection).list_all()
    assert len(features) == FEATURE_VECTOR_COUNT
    assert all(len(feature.vector) == FEATURE_DIMENSIONS for feature in features)


def test_fewer_than_two_feature_vectors_is_a_no_op(connection: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    store_path = tmp_path / "features.parquet"
    write_features(store_path, {"a" * 64: np.array([1.0, 2.0])})

    summary = reduce_and_persist_coordinates(connection, store_path)

    assert summary == CloudSummary(samples_reduced=0)
    assert DuckDBCloudCoordinateRepository(connection).list_all() == ()


def test_an_empty_feature_store_is_a_no_op(connection: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    summary = reduce_and_persist_coordinates(connection, tmp_path / "does-not-exist.parquet")

    assert summary == CloudSummary(samples_reduced=0)


def _failing_upsert(self: DuckDBCloudCoordinateRepository, coordinate: SampleCloudCoordinate) -> None:
    raise OSError("simulated failure")


def test_a_failure_partway_through_leaves_nothing_committed(
    connection: duckdb.DuckDBPyConnection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store_path = _seed_samples_and_features(connection, tmp_path)
    monkeypatch.setattr(DuckDBCloudCoordinateRepository, "upsert", _failing_upsert)

    with pytest.raises(OSError):
        reduce_and_persist_coordinates(connection, store_path)

    assert DuckDBCloudCoordinateRepository(connection).list_all() == ()
    assert DuckDBSampleSpectralFeatureRepository(connection).list_all() == ()


def test_a_second_run_replaces_rather_than_duplicates_coordinates(
    connection: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    store_path = _seed_samples_and_features(connection, tmp_path)
    reduce_and_persist_coordinates(connection, store_path)

    reduce_and_persist_coordinates(connection, store_path)

    assert len(DuckDBCloudCoordinateRepository(connection).list_all()) == FEATURE_VECTOR_COUNT
    assert len(DuckDBSampleSpectralFeatureRepository(connection).list_all()) == FEATURE_VECTOR_COUNT
