from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecloud import features as features_module
from samplecloud.features import FeatureExtractionSummary, extract_features
from samplecore.models.channels import ChannelLayout
from samplecore.models.experiment import Experiment
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository


class _StubFeatureExtractor:
    """A fast, deterministic stand-in for a real backend -- proves the extraction pipeline works
    against any FeatureExtractor, not only the one shipped implementation.
    """

    def extract(self, waveform: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.array([waveform.shape[0], waveform.mean()])


def _store_sample(connection: Connection, library_root: Path, *, hash_seed: int) -> Sample:
    pcm = np.random.default_rng(hash_seed).uniform(-1.0, 1.0, (32, 1))
    sample = Sample(hash=format(hash_seed, "064x"), depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=32)
    PostgresSampleRepository(connection).upsert(sample)
    audio_store.write(library_root, SamplePCM(sample=sample, pcm=pcm))
    return sample


def _create_experiment(connection: Connection) -> int:
    repository = PostgresExperimentRepository(connection)
    experiment_id = repository.next_id()
    repository.insert(
        Experiment(id=experiment_id, backend_name="stub", params={}, created_at=datetime.now(UTC), label=None)
    )
    return experiment_id


def test_extract_features_writes_a_vector_for_every_catalogued_sample(connection: Connection, tmp_path: Path) -> None:
    first = _store_sample(connection, tmp_path, hash_seed=1)
    second = _store_sample(connection, tmp_path, hash_seed=2)
    experiment_id = _create_experiment(connection)

    summary = extract_features(connection, tmp_path, experiment_id, _StubFeatureExtractor())

    assert summary == FeatureExtractionSummary(catalogued=2, already_extracted=0, newly_extracted=2)
    vectors = PostgresSampleFeatureVectorRepository(connection).list_for_experiment(experiment_id)
    assert {vector.sample_hash for vector in vectors} == {first.hash, second.hash}


def test_a_second_run_skips_already_extracted_samples(connection: Connection, tmp_path: Path) -> None:
    _store_sample(connection, tmp_path, hash_seed=1)
    experiment_id = _create_experiment(connection)
    extract_features(connection, tmp_path, experiment_id, _StubFeatureExtractor())
    _store_sample(connection, tmp_path, hash_seed=2)

    summary = extract_features(connection, tmp_path, experiment_id, _StubFeatureExtractor())

    assert summary == FeatureExtractionSummary(catalogued=2, already_extracted=1, newly_extracted=1)


def test_a_different_experiment_extracts_independently(connection: Connection, tmp_path: Path) -> None:
    _store_sample(connection, tmp_path, hash_seed=1)
    first_experiment_id = _create_experiment(connection)
    extract_features(connection, tmp_path, first_experiment_id, _StubFeatureExtractor())

    second_experiment_id = _create_experiment(connection)
    summary = extract_features(connection, tmp_path, second_experiment_id, _StubFeatureExtractor())

    assert summary == FeatureExtractionSummary(catalogued=1, already_extracted=0, newly_extracted=1)


def test_sample_limit_bounds_how_many_new_samples_are_extracted(connection: Connection, tmp_path: Path) -> None:
    _store_sample(connection, tmp_path, hash_seed=1)
    _store_sample(connection, tmp_path, hash_seed=2)
    experiment_id = _create_experiment(connection)

    summary = extract_features(connection, tmp_path, experiment_id, _StubFeatureExtractor(), sample_limit=1)

    assert summary.newly_extracted == 1


def test_an_empty_catalog_extracts_nothing(connection: Connection, tmp_path: Path) -> None:
    experiment_id = _create_experiment(connection)

    summary = extract_features(connection, tmp_path, experiment_id, _StubFeatureExtractor())

    assert summary == FeatureExtractionSummary(catalogued=0, already_extracted=0, newly_extracted=0)


class _InterruptingFeatureExtractor:
    """Fails on its third call, simulating a run stopped partway through extraction."""

    def __init__(self) -> None:
        self.calls = 0

    def extract(self, waveform: NDArray[np.float64]) -> NDArray[np.float64]:
        self.calls += 1
        if self.calls == 3:
            raise OSError("simulated interruption")
        return np.array([waveform.shape[0], waveform.mean()])


def test_an_interruption_loses_at_most_one_checkpoint_of_work(
    connection: Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(features_module, "EXTRACTION_CHECKPOINT_INTERVAL", 2)
    for hash_seed in range(1, 6):
        _store_sample(connection, tmp_path, hash_seed=hash_seed)
    experiment_id = _create_experiment(connection)

    with pytest.raises(OSError, match="simulated interruption"):
        extract_features(connection, tmp_path, experiment_id, _InterruptingFeatureExtractor())

    vectors = PostgresSampleFeatureVectorRepository(connection).list_for_experiment(experiment_id)
    assert len(vectors) == 2
