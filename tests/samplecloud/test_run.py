from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecloud.backends import FeatureExtractor
from samplecloud.experiments import EmbeddingRecipe, ExperimentRefused, ExtractorChanged
from samplecloud.run import (
    REBUILT_RECIPE,
    EmbeddingOptions,
    create_experiment,
    experiment_to_rebuild,
    run_embedding,
)
from samplecore.config import LibraryConfig
from samplecore.models.channels import ChannelLayout
from samplecore.models.cloud import CloudPromotion, SampleCloudCoordinate
from samplecore.models.experiment import Reading
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.repositories.cloud import PostgresCloudCoordinateRepository, PostgresCloudPromotionRepository
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository

SAMPLE_COUNT = 5
STUB_RECIPE = EmbeddingRecipe(backend_name="stub", reading=Reading.NOMINAL, model_name=None)
PROMOTE = EmbeddingOptions(reading=Reading.NOMINAL, sample_limit=None, promote=True)


class _StubFeatureExtractor:
    def extract(self, waveform: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.array([waveform.mean(), waveform.std()])


class _RetrainedFeatureExtractor:
    """Describes the same samples along other axes, the way a descriptor retrained under one name would."""

    def extract(self, waveform: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.array([waveform.std(), waveform.mean()])


def _stub() -> FeatureExtractor:
    return _StubFeatureExtractor()


def _never_built() -> FeatureExtractor:
    raise AssertionError("a pass with nothing to describe builds no extractor")


def _store_samples(connection: Connection, library_root: Path, *, seeds: range) -> None:
    repository = PostgresSampleRepository(connection)
    for seed in seeds:
        pcm = np.random.default_rng(seed).uniform(-1.0, 1.0, (32, 1))
        sample = Sample(hash=format(seed + 1, "064x"), depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=32)
        repository.upsert(sample)
        audio_store.write(library_root, SamplePCM(sample=sample, pcm=pcm))
    connection.commit()


def _config(tmp_path: Path, database_url: str) -> LibraryConfig:
    return LibraryConfig(module_source_directory=tmp_path, library_root=tmp_path, database_url=database_url)


def _promoted(connection: Connection) -> int | None:
    promotion = PostgresCloudPromotionRepository(connection).current()
    return promotion.experiment_id if promotion is not None else None


def test_run_embedding_extracts_and_lays_out_the_whole_catalog(
    connection: Connection, _database_url: str, tmp_path: Path
) -> None:
    _store_samples(connection, tmp_path, seeds=range(SAMPLE_COUNT))
    experiment_id = create_experiment(connection, STUB_RECIPE, label=None, key=None)

    summary = run_embedding(
        _config(tmp_path, _database_url), connection, experiment_id, extractor=_stub, options=PROMOTE
    )

    assert summary.extraction.newly_extracted == SAMPLE_COUNT
    assert summary.reduction is not None
    assert summary.reduction.samples_reduced == SAMPLE_COUNT
    assert len(PostgresCloudCoordinateRepository(connection).list_all()) == SAMPLE_COUNT
    assert _promoted(connection) == experiment_id


def test_run_embedding_respects_the_sample_limit(connection: Connection, _database_url: str, tmp_path: Path) -> None:
    _store_samples(connection, tmp_path, seeds=range(SAMPLE_COUNT))
    experiment_id = create_experiment(connection, STUB_RECIPE, label=None, key=None)

    summary = run_embedding(
        _config(tmp_path, _database_url),
        connection,
        experiment_id,
        extractor=_stub,
        options=EmbeddingOptions(reading=Reading.NOMINAL, sample_limit=1, promote=False),
    )

    assert summary.extraction.newly_extracted == 1


def test_a_pass_over_an_empty_catalog_builds_no_extractor_and_records_no_promotion(
    connection: Connection, _database_url: str, tmp_path: Path
) -> None:
    experiment_id = create_experiment(connection, STUB_RECIPE, label=None, key=None)

    summary = run_embedding(
        _config(tmp_path, _database_url), connection, experiment_id, extractor=_never_built, options=PROMOTE
    )

    assert summary.extraction.cataloged == 0
    assert summary.reduction is not None
    assert summary.reduction.samples_reduced == 0
    assert _promoted(connection) is None


def test_run_embedding_keeps_the_cloud_as_it_was_when_asked_only_to_extract(
    connection: Connection, _database_url: str, tmp_path: Path
) -> None:
    _store_samples(connection, tmp_path, seeds=range(SAMPLE_COUNT))
    experiment_id = create_experiment(connection, STUB_RECIPE, label=None, key=None)

    summary = run_embedding(
        _config(tmp_path, _database_url),
        connection,
        experiment_id,
        extractor=_stub,
        options=EmbeddingOptions(reading=Reading.NOMINAL, sample_limit=None, promote=False),
    )

    assert summary.reduction is None
    assert len(PostgresSampleFeatureVectorRepository(connection).list_for_experiment(experiment_id)) == SAMPLE_COUNT
    assert PostgresCloudCoordinateRepository(connection).list_all() == ()
    assert _promoted(connection) is None


def test_resuming_the_shown_experiment_with_nothing_new_keeps_its_layout(
    connection: Connection, _database_url: str, tmp_path: Path
) -> None:
    config = _config(tmp_path, _database_url)
    _store_samples(connection, tmp_path, seeds=range(SAMPLE_COUNT))
    experiment_id = create_experiment(connection, STUB_RECIPE, label=None, key=None)
    run_embedding(config, connection, experiment_id, extractor=_stub, options=PROMOTE)
    laid_out = PostgresCloudCoordinateRepository(connection).revision()

    summary = run_embedding(config, connection, experiment_id, extractor=_never_built, options=PROMOTE)

    assert summary.reduction is None
    assert PostgresCloudCoordinateRepository(connection).revision() == laid_out


def test_promoting_an_experiment_the_cloud_does_not_show_lays_it_out(
    connection: Connection, _database_url: str, tmp_path: Path
) -> None:
    config = _config(tmp_path, _database_url)
    _store_samples(connection, tmp_path, seeds=range(SAMPLE_COUNT))
    shown = create_experiment(connection, STUB_RECIPE, label=None, key=None)
    run_embedding(config, connection, shown, extractor=_stub, options=PROMOTE)
    measured = create_experiment(connection, STUB_RECIPE, label=None, key=None)
    run_embedding(
        config,
        connection,
        measured,
        extractor=_stub,
        options=EmbeddingOptions(reading=Reading.NOMINAL, sample_limit=None, promote=False),
    )

    summary = run_embedding(config, connection, measured, extractor=_never_built, options=PROMOTE)

    assert summary.reduction is not None
    assert _promoted(connection) == measured


def test_resuming_with_an_extractor_that_describes_its_samples_again_adds_the_new_ones(
    connection: Connection, _database_url: str, tmp_path: Path
) -> None:
    config = _config(tmp_path, _database_url)
    _store_samples(connection, tmp_path, seeds=range(2))
    experiment_id = create_experiment(connection, STUB_RECIPE, label=None, key=None)
    run_embedding(config, connection, experiment_id, extractor=_stub, options=PROMOTE)
    _store_samples(connection, tmp_path, seeds=range(2, SAMPLE_COUNT))

    summary = run_embedding(config, connection, experiment_id, extractor=_stub, options=PROMOTE)

    assert summary.extraction.newly_extracted == SAMPLE_COUNT - 2


def test_resuming_with_a_changed_extractor_is_refused_before_any_vector_is_added(
    connection: Connection, _database_url: str, tmp_path: Path
) -> None:
    config = _config(tmp_path, _database_url)
    _store_samples(connection, tmp_path, seeds=range(2))
    experiment_id = create_experiment(connection, STUB_RECIPE, label=None, key=None)
    run_embedding(config, connection, experiment_id, extractor=_stub, options=PROMOTE)
    _store_samples(connection, tmp_path, seeds=range(2, SAMPLE_COUNT))

    with pytest.raises(ExtractorChanged, match=f"experiment {experiment_id}"):
        run_embedding(config, connection, experiment_id, extractor=_RetrainedFeatureExtractor, options=PROMOTE)

    assert len(PostgresSampleFeatureVectorRepository(connection).list_for_experiment(experiment_id)) == 2


def test_create_experiment_records_the_recipe_and_label(connection: Connection) -> None:
    recipe = EmbeddingRecipe(backend_name="learned", reading=Reading.HEARD_RATE, model_name="tiny")

    experiment = PostgresExperimentRepository(connection).get(
        create_experiment(connection, recipe, label="one", key=None)
    )

    assert experiment is not None
    assert experiment.params == {"reading": "heard_rate", "model": "tiny"}
    assert experiment.label == "one"


def test_a_rebuild_resumes_the_experiment_the_cloud_shows(connection: Connection) -> None:
    shown = create_experiment(connection, STUB_RECIPE, label=None, key=None)
    PostgresCloudPromotionRepository(connection).record(
        CloudPromotion(experiment_id=shown, promoted_at=datetime.now(UTC))
    )
    connection.commit()

    assert experiment_to_rebuild(connection) == shown


def test_a_rebuild_of_an_empty_cloud_opens_the_default_experiment_and_records_it_at_once(
    connection: Connection,
) -> None:
    experiment_id = experiment_to_rebuild(connection)
    connection.rollback()

    experiment = PostgresExperimentRepository(connection).get(experiment_id)
    assert experiment is not None
    assert experiment.backend_name == REBUILT_RECIPE.backend_name
    assert experiment.params == REBUILT_RECIPE.parameters
    assert _promoted(connection) == experiment_id
    assert experiment_to_rebuild(connection) == experiment_id


def test_a_rebuild_of_a_cloud_with_no_record_of_its_experiment_is_refused(
    connection: Connection, tmp_path: Path
) -> None:
    _store_samples(connection, tmp_path, seeds=range(1))
    PostgresCloudCoordinateRepository(connection).upsert(
        SampleCloudCoordinate(sample_hash=format(1, "064x"), x=0.0, y=0.0, computed_at=datetime.now(UTC))
    )
    connection.commit()

    with pytest.raises(ExperimentRefused, match="--experiment-id"):
        experiment_to_rebuild(connection)
