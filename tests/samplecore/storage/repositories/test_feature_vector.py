from __future__ import annotations

from datetime import UTC, datetime

import psycopg
import pytest
from sqlalchemy import Connection

from samplecore.models.experiment import Experiment, SampleFeatureVector
from samplecore.models.sample import Sample
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository


def _create_experiment(connection: Connection, *, backend_name: str = "librosa") -> int:
    repository = PostgresExperimentRepository(connection)
    experiment_id = repository.next_id()
    repository.insert(
        Experiment(id=experiment_id, backend_name=backend_name, params={}, created_at=datetime.now(UTC), label=None)
    )
    return experiment_id


def _vector(
    experiment_id: int, sample_hash: str, *, values: tuple[float, ...] = (0.1, 0.2, 0.3)
) -> SampleFeatureVector:
    return SampleFeatureVector(
        experiment_id=experiment_id, sample_hash=sample_hash, vector=values, computed_at=datetime.now(UTC)
    )


def test_list_for_experiment_on_an_empty_table_returns_nothing(connection: Connection) -> None:
    experiment_id = _create_experiment(connection)

    assert PostgresSampleFeatureVectorRepository(connection).list_for_experiment(experiment_id) == ()


def test_insert_many_with_no_vectors_is_a_no_op(connection: Connection) -> None:
    PostgresSampleFeatureVectorRepository(connection).insert_many([])


def test_inserted_vectors_round_trip_through_list_for_experiment(connection: Connection, stored_sample: Sample) -> None:
    experiment_id = _create_experiment(connection)
    vector = _vector(experiment_id, stored_sample.hash)

    PostgresSampleFeatureVectorRepository(connection).insert_many([vector])

    assert PostgresSampleFeatureVectorRepository(connection).list_for_experiment(experiment_id) == (vector,)


def test_two_experiments_hold_independent_vectors_for_the_same_sample(
    connection: Connection, stored_sample: Sample
) -> None:
    first_experiment_id = _create_experiment(connection, backend_name="librosa")
    second_experiment_id = _create_experiment(connection, backend_name="invariant_v2")
    repository = PostgresSampleFeatureVectorRepository(connection)
    repository.insert_many([_vector(first_experiment_id, stored_sample.hash, values=(1.0, 2.0))])
    repository.insert_many([_vector(second_experiment_id, stored_sample.hash, values=(3.0, 4.0))])

    first_vectors = repository.list_for_experiment(first_experiment_id)
    second_vectors = repository.list_for_experiment(second_experiment_id)

    assert [vector.vector for vector in first_vectors] == [(1.0, 2.0)]
    assert [vector.vector for vector in second_vectors] == [(3.0, 4.0)]


def test_inserting_a_vector_for_an_uncatalogued_sample_fails(connection: Connection) -> None:
    experiment_id = _create_experiment(connection)

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        PostgresSampleFeatureVectorRepository(connection).insert_many([_vector(experiment_id, "f" * 64)])


def test_inserting_a_vector_for_an_unknown_experiment_fails(connection: Connection, stored_sample: Sample) -> None:
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        PostgresSampleFeatureVectorRepository(connection).insert_many([_vector(999_999, stored_sample.hash)])
