from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecloud.run import resolve_experiment, run_embedding
from samplecore.config import LibraryConfig
from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.repositories.cloud import PostgresCloudCoordinateRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository

SAMPLE_COUNT = 4


class _StubFeatureExtractor:
    def extract(self, waveform: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.array([waveform.mean(), waveform.std()])


def _seed_catalog(connection: Connection, library_root: Path) -> None:
    repository = PostgresSampleRepository(connection)
    for seed in range(SAMPLE_COUNT):
        pcm = np.random.default_rng(seed).uniform(-1.0, 1.0, (32, 1))
        sample = Sample(hash=format(seed + 1, "064x"), depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=32)
        repository.upsert(sample)
        audio_store.write(library_root, SamplePCM(sample=sample, pcm=pcm))


def _config(tmp_path: Path, database_url: str) -> LibraryConfig:
    return LibraryConfig(module_source_directory=tmp_path, library_root=tmp_path, database_url=database_url)


def test_run_embedding_extracts_and_reduces_the_whole_catalog(
    connection: Connection, _database_url: str, tmp_path: Path
) -> None:
    _seed_catalog(connection, tmp_path)
    config = _config(tmp_path, _database_url)
    experiment_id = resolve_experiment(connection, backend_name="stub")

    summary = run_embedding(config, connection, _StubFeatureExtractor(), experiment_id)

    assert summary.extraction.newly_extracted == SAMPLE_COUNT
    assert summary.reduction.samples_reduced == SAMPLE_COUNT
    vectors = PostgresSampleFeatureVectorRepository(connection).list_for_experiment(experiment_id)
    assert len(vectors) == SAMPLE_COUNT
    assert len(PostgresCloudCoordinateRepository(connection).list_all()) == SAMPLE_COUNT


def test_run_embedding_respects_the_sample_limit(connection: Connection, _database_url: str, tmp_path: Path) -> None:
    _seed_catalog(connection, tmp_path)
    config = _config(tmp_path, _database_url)
    experiment_id = resolve_experiment(connection, backend_name="stub")

    summary = run_embedding(config, connection, _StubFeatureExtractor(), experiment_id, sample_limit=1)

    assert summary.extraction.newly_extracted == 1


def test_run_embedding_on_an_empty_catalog_reduces_nothing(
    connection: Connection, _database_url: str, tmp_path: Path
) -> None:
    config = _config(tmp_path, _database_url)
    experiment_id = resolve_experiment(connection, backend_name="stub")

    summary = run_embedding(config, connection, _StubFeatureExtractor(), experiment_id)

    assert summary.extraction.cataloged == 0
    assert summary.reduction.samples_reduced == 0


def test_resolve_experiment_creates_a_new_experiment_when_no_id_is_given(connection: Connection) -> None:
    experiment_id = resolve_experiment(connection, backend_name="stub", label="a note")

    assert isinstance(experiment_id, int)


def test_resolve_experiment_resumes_an_existing_experiment(connection: Connection) -> None:
    first_call_id = resolve_experiment(connection, backend_name="stub")

    resumed_id = resolve_experiment(connection, backend_name="stub", experiment_id=first_call_id)

    assert resumed_id == first_call_id


def test_resolve_experiment_against_an_unknown_id_fails(connection: Connection) -> None:
    with pytest.raises(ValueError, match="No experiment"):
        resolve_experiment(connection, backend_name="stub", experiment_id=999_999)
