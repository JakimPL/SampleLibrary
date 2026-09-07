from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Connection

from samplecore.models.experiment import Experiment
from samplecore.storage.repositories.experiment import PostgresExperimentRepository


def _build_experiment(experiment_id: int, *, backend_name: str = "librosa", label: str | None = None) -> Experiment:
    return Experiment(
        id=experiment_id, backend_name=backend_name, params={"root_hz": 60.0}, created_at=datetime.now(UTC), label=label
    )


def test_next_id_produces_increasing_values(connection: Connection) -> None:
    repository = PostgresExperimentRepository(connection)

    first_id = repository.next_id()
    second_id = repository.next_id()

    assert second_id > first_id


def test_an_inserted_experiment_round_trips_through_get(connection: Connection) -> None:
    repository = PostgresExperimentRepository(connection)
    experiment = _build_experiment(repository.next_id(), label="32pt envelope + 20-coef CQHC")

    repository.insert(experiment)

    assert repository.get(experiment.id) == experiment


def test_get_on_an_unknown_id_returns_none(connection: Connection) -> None:
    assert PostgresExperimentRepository(connection).get(999_999) is None


def test_params_round_trip_as_a_structured_mapping(connection: Connection) -> None:
    repository = PostgresExperimentRepository(connection)
    experiment = Experiment(
        id=repository.next_id(),
        backend_name="invariant_v2",
        params={"root_hz": 60.0, "floor_db": 72.0},
        created_at=datetime.now(UTC),
        label=None,
    )
    repository.insert(experiment)

    reloaded = repository.get(experiment.id)

    assert reloaded is not None
    assert reloaded.params == {"root_hz": 60.0, "floor_db": 72.0}
