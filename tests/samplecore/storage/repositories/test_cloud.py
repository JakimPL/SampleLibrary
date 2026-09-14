from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Connection, func, select

from samplecore.models.cloud import CloudPromotion, ModuleCloudCoordinate, SampleCloudCoordinate
from samplecore.models.module import Module
from samplecore.models.sample import Sample
from samplecore.storage.database import cloud_promotion
from samplecore.storage.repositories.cloud import (
    PostgresCloudCoordinateRepository,
    PostgresCloudPromotionRepository,
    PostgresModuleCloudCoordinateRepository,
)
from samplecore.storage.repositories.experiment import PostgresExperimentRepository


def _coordinate(sample_hash: str, *, x: float = 1.0, y: float = 2.0) -> SampleCloudCoordinate:
    return SampleCloudCoordinate(sample_hash=sample_hash, x=x, y=y, computed_at=datetime.now(UTC))


def _module_coordinate(module_hash: str, *, x: float = 1.0, y: float = 2.0) -> ModuleCloudCoordinate:
    return ModuleCloudCoordinate(module_hash=module_hash, x=x, y=y, computed_at=datetime.now(UTC))


def test_list_all_on_an_empty_table_returns_nothing(connection: Connection) -> None:
    assert PostgresCloudCoordinateRepository(connection).list_all() == ()


def test_a_coordinate_round_trips_through_list_all(connection: Connection, stored_sample: Sample) -> None:
    repository = PostgresCloudCoordinateRepository(connection)
    coordinate = _coordinate(stored_sample.hash)

    repository.upsert(coordinate)

    assert repository.list_all() == (coordinate,)


def test_upserting_the_same_sample_again_replaces_its_coordinate(connection: Connection, stored_sample: Sample) -> None:
    repository = PostgresCloudCoordinateRepository(connection)
    repository.upsert(_coordinate(stored_sample.hash, x=1.0, y=2.0))
    refined = _coordinate(stored_sample.hash, x=3.0, y=4.0)

    repository.upsert(refined)

    assert repository.list_all() == (refined,)


def test_list_all_returns_one_coordinate_per_sample(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    repository = PostgresCloudCoordinateRepository(connection)
    first = _coordinate(stored_sample.hash)
    second = _coordinate(stored_sample_b.hash)

    repository.upsert(first)
    repository.upsert(second)

    assert set(repository.list_all()) == {first, second}


def test_module_list_all_on_an_empty_table_returns_nothing(connection: Connection) -> None:
    assert PostgresModuleCloudCoordinateRepository(connection).list_all() == ()


def test_a_module_coordinate_round_trips_through_list_all(connection: Connection, stored_module: Module) -> None:
    repository = PostgresModuleCloudCoordinateRepository(connection)
    coordinate = _module_coordinate(stored_module.hash)

    repository.upsert(coordinate)

    assert repository.list_all() == (coordinate,)


def test_upserting_the_same_module_again_replaces_its_coordinate(connection: Connection, stored_module: Module) -> None:
    repository = PostgresModuleCloudCoordinateRepository(connection)
    repository.upsert(_module_coordinate(stored_module.hash, x=1.0, y=2.0))
    refined = _module_coordinate(stored_module.hash, x=3.0, y=4.0)

    repository.upsert(refined)

    assert repository.list_all() == (refined,)


def test_module_list_all_returns_one_coordinate_per_module(
    connection: Connection, stored_module: Module, stored_module_b: Module
) -> None:
    repository = PostgresModuleCloudCoordinateRepository(connection)
    first = _module_coordinate(stored_module.hash)
    second = _module_coordinate(stored_module_b.hash)

    repository.upsert(first)
    repository.upsert(second)

    assert set(repository.list_all()) == {first, second}


def test_replace_all_replaces_whatever_was_persisted_before(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    repository = PostgresCloudCoordinateRepository(connection)
    repository.upsert(_coordinate(stored_sample.hash))
    replacement = _coordinate(stored_sample_b.hash)

    repository.replace_all([replacement])

    assert repository.list_all() == (replacement,)


def test_replace_all_with_an_empty_sequence_clears_the_table(connection: Connection, stored_sample: Sample) -> None:
    repository = PostgresCloudCoordinateRepository(connection)
    repository.upsert(_coordinate(stored_sample.hash))

    repository.replace_all([])

    assert repository.list_all() == ()


def test_module_replace_all_replaces_whatever_was_persisted_before(
    connection: Connection, stored_module: Module, stored_module_b: Module
) -> None:
    repository = PostgresModuleCloudCoordinateRepository(connection)
    repository.upsert(_module_coordinate(stored_module.hash))
    replacement = _module_coordinate(stored_module_b.hash)

    repository.replace_all([replacement])

    assert repository.list_all() == (replacement,)


def test_module_replace_all_with_an_empty_sequence_clears_the_table(
    connection: Connection, stored_module: Module
) -> None:
    repository = PostgresModuleCloudCoordinateRepository(connection)
    repository.upsert(_module_coordinate(stored_module.hash))

    repository.replace_all([])

    assert repository.list_all() == ()


def _experiment(connection: Connection) -> int:
    return PostgresExperimentRepository(connection).create(backend_name="librosa", label=None, params={}, key=None)


def test_no_experiment_is_on_show_before_one_is_recorded(connection: Connection) -> None:
    assert PostgresCloudPromotionRepository(connection).current() is None


def test_recording_a_promotion_replaces_the_one_on_show(connection: Connection) -> None:
    repository = PostgresCloudPromotionRepository(connection)
    first, second = _experiment(connection), _experiment(connection)
    repository.record(CloudPromotion(experiment_id=first, promoted_at=datetime.now(UTC)))
    promoted = CloudPromotion(experiment_id=second, promoted_at=datetime.now(UTC))

    repository.record(promoted)

    assert repository.current() == promoted
    assert connection.execute(select(func.count()).select_from(cloud_promotion)).scalar_one() == 1
