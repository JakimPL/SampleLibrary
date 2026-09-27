from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import umap
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecloud import reduce as reduce_module
from samplecloud.reduce import MINIMUM_SAMPLES_FOR_REDUCTION, CloudSummary, reduce_and_persist_coordinates
from samplecloud.stages import LayoutStages
from samplecore.models.channels import ChannelLayout
from samplecore.models.cloud import SampleCloudCoordinate
from samplecore.models.experiment import Experiment, SampleFeatureVector
from samplecore.models.sample import Sample
from samplecore.storage.repositories.cloud import PostgresCloudCoordinateRepository, PostgresCloudPromotionRepository
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.spectral import PostgresSampleSpectralFeatureRepository

FEATURE_VECTOR_COUNT = 6
FEATURE_DIMENSIONS = 4
# Enough points to fit with the neighbor graph found apart, once the minimum for that is lowered to it.
APPROXIMATE_TEST_POINTS = 60


@pytest.fixture
def stages_directory(tmp_path: Path) -> Path:
    return tmp_path / "layouts"


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


def test_reduce_persists_one_coordinate_per_feature_vector(connection: Connection, stages_directory: Path) -> None:
    experiment_id = _seed_samples_and_features(connection)

    summary = reduce_and_persist_coordinates(connection, experiment_id, stages_directory=stages_directory)

    assert summary == CloudSummary(samples_reduced=FEATURE_VECTOR_COUNT)
    assert len(PostgresCloudCoordinateRepository(connection).list_all()) == FEATURE_VECTOR_COUNT


def test_reduce_also_persists_a_standardized_feature_vector_per_sample(
    connection: Connection, stages_directory: Path
) -> None:
    experiment_id = _seed_samples_and_features(connection)

    reduce_and_persist_coordinates(connection, experiment_id, stages_directory=stages_directory)

    features = PostgresSampleSpectralFeatureRepository(connection).list_all()
    assert len(features) == FEATURE_VECTOR_COUNT
    assert all(len(feature.vector) == FEATURE_DIMENSIONS for feature in features)


@pytest.mark.parametrize("count", range(1, MINIMUM_SAMPLES_FOR_REDUCTION))
def test_fewer_vectors_than_a_layout_needs_leave_the_cloud_and_its_record_alone(
    count: int, connection: Connection, stages_directory: Path
) -> None:
    experiment_id = _seed_samples_and_features(connection, count=count)

    summary = reduce_and_persist_coordinates(connection, experiment_id, stages_directory=stages_directory)

    assert summary == CloudSummary(samples_reduced=0)
    assert PostgresCloudCoordinateRepository(connection).list_all() == ()
    assert PostgresCloudPromotionRepository(connection).current() is None


@pytest.mark.parametrize("count", range(MINIMUM_SAMPLES_FOR_REDUCTION, MINIMUM_SAMPLES_FOR_REDUCTION + 5))
def test_the_smallest_experiments_a_layout_accepts_are_laid_out(
    count: int, connection: Connection, stages_directory: Path
) -> None:
    experiment_id = _seed_samples_and_features(connection, count=count)

    summary = reduce_and_persist_coordinates(connection, experiment_id, stages_directory=stages_directory)

    assert summary == CloudSummary(samples_reduced=count)


def test_a_layout_records_its_experiment_as_the_one_the_cloud_shows(
    connection: Connection, stages_directory: Path
) -> None:
    experiment_id = _seed_samples_and_features(connection)

    reduce_and_persist_coordinates(connection, experiment_id, stages_directory=stages_directory)

    promotion = PostgresCloudPromotionRepository(connection).current()
    assert promotion is not None
    assert promotion.experiment_id == experiment_id


def test_an_experiment_with_no_feature_vectors_yet_is_a_no_op(connection: Connection, stages_directory: Path) -> None:
    experiment_id = _create_experiment(connection)

    summary = reduce_and_persist_coordinates(connection, experiment_id, stages_directory=stages_directory)

    assert summary == CloudSummary(samples_reduced=0)


def _failing_replace_all(self: PostgresCloudCoordinateRepository, coordinates: Sequence[SampleCloudCoordinate]) -> None:
    raise OSError("simulated failure")


def test_a_failure_partway_through_leaves_nothing_committed(
    connection: Connection, monkeypatch: pytest.MonkeyPatch, stages_directory: Path
) -> None:
    experiment_id = _seed_samples_and_features(connection)
    monkeypatch.setattr(PostgresCloudCoordinateRepository, "replace_all", _failing_replace_all)

    with pytest.raises(OSError):
        reduce_and_persist_coordinates(connection, experiment_id, stages_directory=stages_directory)

    assert PostgresCloudCoordinateRepository(connection).list_all() == ()
    assert PostgresSampleSpectralFeatureRepository(connection).list_all() == ()
    assert PostgresCloudPromotionRepository(connection).current() is None


def test_a_second_run_replaces_rather_than_duplicates_coordinates(
    connection: Connection, stages_directory: Path
) -> None:
    experiment_id = _seed_samples_and_features(connection)
    reduce_and_persist_coordinates(connection, experiment_id, stages_directory=stages_directory)

    reduce_and_persist_coordinates(connection, experiment_id, stages_directory=stages_directory)

    assert len(PostgresCloudCoordinateRepository(connection).list_all()) == FEATURE_VECTOR_COUNT
    assert len(PostgresSampleSpectralFeatureRepository(connection).list_all()) == FEATURE_VECTOR_COUNT


def test_promoting_a_different_experiment_replaces_the_previous_coordinates(
    connection: Connection, stages_directory: Path
) -> None:
    first_experiment_id = _seed_samples_and_features(connection)
    reduce_and_persist_coordinates(connection, first_experiment_id, stages_directory=stages_directory)

    second_experiment_id = _seed_samples_and_features(connection)
    reduce_and_persist_coordinates(connection, second_experiment_id, stages_directory=stages_directory)

    assert len(PostgresCloudCoordinateRepository(connection).list_all()) == FEATURE_VECTOR_COUNT
    assert len(PostgresSampleSpectralFeatureRepository(connection).list_all()) == FEATURE_VECTOR_COUNT


class LayoutStopped(RuntimeError):
    pass


def _laid_out(connection: Connection) -> dict[str, tuple[float, float]]:
    return {
        coordinate.sample_hash: (coordinate.x, coordinate.y)
        for coordinate in PostgresCloudCoordinateRepository(connection).list_all()
    }


def test_a_layout_stopped_after_its_neighbor_search_fits_from_the_kept_graph_as_a_straight_run_would(
    connection: Connection, stages_directory: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reduce_module, "APPROXIMATE_SEARCH_MINIMUM", APPROXIMATE_TEST_POINTS)
    experiment_id = _seed_samples_and_features(connection, count=APPROXIMATE_TEST_POINTS)
    reduce_and_persist_coordinates(connection, experiment_id, stages_directory=tmp_path / "straight")
    straight = _laid_out(connection)
    keep_coordinates = LayoutStages.keep_coordinates

    def stop_before_keeping(stages: LayoutStages, coordinates: object) -> None:
        raise LayoutStopped("stopped after the neighbor search")

    monkeypatch.setattr(LayoutStages, "keep_coordinates", stop_before_keeping)
    with pytest.raises(LayoutStopped):
        reduce_and_persist_coordinates(connection, experiment_id, stages_directory=stages_directory)
    monkeypatch.setattr(LayoutStages, "keep_coordinates", keep_coordinates)

    def search_again(*arguments: object, **keywords: object) -> None:
        raise AssertionError("the kept neighbor graph was searched for again")

    monkeypatch.setattr(umap.umap_, "nearest_neighbors", search_again)

    reduce_and_persist_coordinates(connection, experiment_id, stages_directory=stages_directory)

    assert _laid_out(connection) == straight
    assert not list(stages_directory.iterdir())
