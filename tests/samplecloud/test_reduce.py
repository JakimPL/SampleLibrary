from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import numpy as np
import pytest
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecloud.reduce import CloudSummary, reduce_and_persist_coordinates
from samplecore.models.channels import ChannelLayout
from samplecore.models.cloud import SampleCloudCoordinate
from samplecore.models.experiment import Experiment, SampleFeatureVector
from samplecore.models.sample import Sample
from samplecore.storage.repositories.cloud import PostgresCloudCoordinateRepository
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.spectral import PostgresSampleSpectralFeatureRepository

FEATURE_VECTOR_COUNT = 6
FEATURE_DIMENSIONS = 4


def _create_experiment(connection: Connection) -> int:
    repository = PostgresExperimentRepository(connection)
    experiment_id = repository.next_id()
    repository.insert(
        Experiment(id=experiment_id, backend_name="stub", params={}, created_at=datetime.now(UTC), label=None)
    )
    return experiment_id


def _seed_samples_and_features(connection: Connection, *, count: int = FEATURE_VECTOR_COUNT) -> int:
    sample_repository = PostgresSampleRepository(connection)
    experiment_id = _create_experiment(connection)
    vectors = []
    for seed in range(count):
        sample_hash = format(seed + 1, "064x")
        sample_repository.upsert(
            Sample(hash=sample_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=32)
        )
        vector = tuple(np.random.default_rng(seed).uniform(-1.0, 1.0, FEATURE_DIMENSIONS))
        vectors.append(
            SampleFeatureVector(
                experiment_id=experiment_id, sample_hash=sample_hash, vector=vector, computed_at=datetime.now(UTC)
            )
        )
    PostgresSampleFeatureVectorRepository(connection).insert_many(vectors)
    return experiment_id


def test_reduce_persists_one_coordinate_per_feature_vector(connection: Connection) -> None:
    experiment_id = _seed_samples_and_features(connection)

    summary = reduce_and_persist_coordinates(connection, experiment_id)

    assert summary == CloudSummary(samples_reduced=FEATURE_VECTOR_COUNT)
    assert len(PostgresCloudCoordinateRepository(connection).list_all()) == FEATURE_VECTOR_COUNT


def test_reduce_also_persists_a_standardized_feature_vector_per_sample(connection: Connection) -> None:
    experiment_id = _seed_samples_and_features(connection)

    reduce_and_persist_coordinates(connection, experiment_id)

    features = PostgresSampleSpectralFeatureRepository(connection).list_all()
    assert len(features) == FEATURE_VECTOR_COUNT
    assert all(len(feature.vector) == FEATURE_DIMENSIONS for feature in features)


def test_fewer_than_two_feature_vectors_is_a_no_op(connection: Connection) -> None:
    experiment_id = _seed_samples_and_features(connection, count=1)

    summary = reduce_and_persist_coordinates(connection, experiment_id)

    assert summary == CloudSummary(samples_reduced=0)
    assert PostgresCloudCoordinateRepository(connection).list_all() == ()


def test_an_experiment_with_no_feature_vectors_yet_is_a_no_op(connection: Connection) -> None:
    experiment_id = _create_experiment(connection)

    summary = reduce_and_persist_coordinates(connection, experiment_id)

    assert summary == CloudSummary(samples_reduced=0)


def _failing_replace_all(self: PostgresCloudCoordinateRepository, coordinates: Sequence[SampleCloudCoordinate]) -> None:
    raise OSError("simulated failure")


def test_a_failure_partway_through_leaves_nothing_committed(
    connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    experiment_id = _seed_samples_and_features(connection)
    monkeypatch.setattr(PostgresCloudCoordinateRepository, "replace_all", _failing_replace_all)

    with pytest.raises(OSError):
        reduce_and_persist_coordinates(connection, experiment_id)

    assert PostgresCloudCoordinateRepository(connection).list_all() == ()
    assert PostgresSampleSpectralFeatureRepository(connection).list_all() == ()


def test_a_second_run_replaces_rather_than_duplicates_coordinates(connection: Connection) -> None:
    experiment_id = _seed_samples_and_features(connection)
    reduce_and_persist_coordinates(connection, experiment_id)

    reduce_and_persist_coordinates(connection, experiment_id)

    assert len(PostgresCloudCoordinateRepository(connection).list_all()) == FEATURE_VECTOR_COUNT
    assert len(PostgresSampleSpectralFeatureRepository(connection).list_all()) == FEATURE_VECTOR_COUNT


def test_promoting_a_different_experiment_replaces_the_previous_coordinates(connection: Connection) -> None:
    first_experiment_id = _seed_samples_and_features(connection)
    reduce_and_persist_coordinates(connection, first_experiment_id)

    second_experiment_id = _seed_samples_and_features(connection)
    reduce_and_persist_coordinates(connection, second_experiment_id)

    assert len(PostgresCloudCoordinateRepository(connection).list_all()) == FEATURE_VECTOR_COUNT
    assert len(PostgresSampleSpectralFeatureRepository(connection).list_all()) == FEATURE_VECTOR_COUNT
