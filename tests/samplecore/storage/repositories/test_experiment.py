from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import Connection
from sqlalchemy.exc import IntegrityError

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


def test_an_experiment_filed_under_a_key_is_found_by_it(connection: Connection) -> None:
    repository = PostgresExperimentRepository(connection)

    experiment_id = repository.create(backend_name="clap", label=None, params={}, key="clap-nominal-195c3a3e")

    filed = repository.get_by_key("clap-nominal-195c3a3e")
    assert filed is not None
    assert filed.id == experiment_id
    assert filed.key == "clap-nominal-195c3a3e"
    assert repository.get_by_key("clap-heard-195c3a3e") is None


def test_one_key_files_one_experiment(connection: Connection) -> None:
    repository = PostgresExperimentRepository(connection)
    repository.create(backend_name="clap", label=None, params={}, key="teacher")

    with pytest.raises(IntegrityError):
        repository.create(backend_name="clap", label=None, params={}, key="teacher")


@pytest.mark.parametrize("key", ["", "Teacher", "-teacher", "teacher key", "a" * 129], ids=repr)
def test_a_key_outside_its_alphabet_is_refused(key: str) -> None:
    with pytest.raises(ValidationError):
        Experiment(id=1, backend_name="clap", params={}, created_at=datetime.now(UTC), key=key)
