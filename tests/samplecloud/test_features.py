from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pytest
from numpy.typing import NDArray
from trackmod.core.samples.depth import BitDepth

from samplecloud import features as features_module
from samplecloud.feature_store import read_features
from samplecloud.features import FeatureExtractionSummary, extract_features
from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.repositories.sample import DuckDBSampleRepository


class _StubFeatureExtractor:
    """A fast, deterministic stand-in for a real backend -- proves the extraction pipeline works
    against any FeatureExtractor, not only the one shipped implementation.
    """

    def extract(self, waveform: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.array([waveform.shape[0], waveform.mean()])


def _store_sample(connection: duckdb.DuckDBPyConnection, library_root: Path, *, hash_seed: int) -> Sample:
    pcm = np.random.default_rng(hash_seed).uniform(-1.0, 1.0, (32, 1))
    sample = Sample(hash=format(hash_seed, "064x"), depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=32)
    DuckDBSampleRepository(connection).upsert(sample)
    audio_store.write(library_root, SamplePCM(sample=sample, pcm=pcm))
    return sample


def test_extract_features_writes_a_vector_for_every_catalogued_sample(
    connection: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    first = _store_sample(connection, tmp_path, hash_seed=1)
    second = _store_sample(connection, tmp_path, hash_seed=2)
    store_path = tmp_path / "features.parquet"

    summary = extract_features(connection, tmp_path, store_path, _StubFeatureExtractor())

    assert summary == FeatureExtractionSummary(catalogued=2, already_extracted=0, newly_extracted=2)
    assert read_features(store_path).keys() == {first.hash, second.hash}


def test_a_second_run_skips_already_extracted_samples(connection: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    _store_sample(connection, tmp_path, hash_seed=1)
    store_path = tmp_path / "features.parquet"
    extract_features(connection, tmp_path, store_path, _StubFeatureExtractor())
    _store_sample(connection, tmp_path, hash_seed=2)

    summary = extract_features(connection, tmp_path, store_path, _StubFeatureExtractor())

    assert summary == FeatureExtractionSummary(catalogued=2, already_extracted=1, newly_extracted=1)


def test_sample_limit_bounds_how_many_new_samples_are_extracted(
    connection: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _store_sample(connection, tmp_path, hash_seed=1)
    _store_sample(connection, tmp_path, hash_seed=2)
    store_path = tmp_path / "features.parquet"

    summary = extract_features(connection, tmp_path, store_path, _StubFeatureExtractor(), sample_limit=1)

    assert summary.newly_extracted == 1


def test_an_empty_catalog_extracts_nothing(connection: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    summary = extract_features(connection, tmp_path, tmp_path / "features.parquet", _StubFeatureExtractor())

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
    connection: duckdb.DuckDBPyConnection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(features_module, "FEATURE_STORE_CHECKPOINT_INTERVAL", 2)
    for hash_seed in range(1, 6):
        _store_sample(connection, tmp_path, hash_seed=hash_seed)
    store_path = tmp_path / "features.parquet"

    with pytest.raises(OSError, match="simulated interruption"):
        extract_features(connection, tmp_path, store_path, _InterruptingFeatureExtractor())

    assert len(read_features(store_path)) == 2
