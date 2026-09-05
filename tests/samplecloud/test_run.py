from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
from numpy.typing import NDArray
from trackmod.core.samples.depth import BitDepth

from samplecloud.run import run_embedding
from samplecore.config import LibraryConfig
from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.repositories.cloud import DuckDBCloudCoordinateRepository
from samplecore.storage.repositories.sample import DuckDBSampleRepository

SAMPLE_COUNT = 4


class _StubFeatureExtractor:
    def extract(self, waveform: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.array([waveform.mean(), waveform.std()])


def _seed_catalog(connection: duckdb.DuckDBPyConnection, library_root: Path) -> None:
    repository = DuckDBSampleRepository(connection)
    for seed in range(SAMPLE_COUNT):
        pcm = np.random.default_rng(seed).uniform(-1.0, 1.0, (32, 1))
        sample = Sample(hash=format(seed + 1, "064x"), depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=32)
        repository.upsert(sample)
        audio_store.write(library_root, SamplePCM(sample=sample, pcm=pcm))


def test_run_embedding_extracts_and_reduces_the_whole_catalog(
    connection: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_catalog(connection, tmp_path)
    config = LibraryConfig(module_source_directory=tmp_path, library_root=tmp_path)

    summary = run_embedding(config, connection, _StubFeatureExtractor())

    assert summary.extraction.newly_extracted == SAMPLE_COUNT
    assert summary.reduction.samples_reduced == SAMPLE_COUNT
    assert (config.resolved_cloud_artifact_directory / "features.parquet").is_file()
    assert len(DuckDBCloudCoordinateRepository(connection).list_all()) == SAMPLE_COUNT


def test_run_embedding_respects_the_sample_limit(connection: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    _seed_catalog(connection, tmp_path)
    config = LibraryConfig(module_source_directory=tmp_path, library_root=tmp_path)

    summary = run_embedding(config, connection, _StubFeatureExtractor(), sample_limit=1)

    assert summary.extraction.newly_extracted == 1


def test_run_embedding_on_an_empty_catalog_reduces_nothing(
    connection: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    config = LibraryConfig(module_source_directory=tmp_path, library_root=tmp_path)

    summary = run_embedding(config, connection, _StubFeatureExtractor())

    assert summary.extraction.catalogued == 0
    assert summary.reduction.samples_reduced == 0
