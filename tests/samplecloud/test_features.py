from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecloud import features as features_module
from samplecloud.backends import FeatureExtractor
from samplecloud.features import FeatureExtractionSummary, FeaturePass, extract_features, pending_samples
from samplecloud.hearing import Hearing, hearing_for
from samplecore.models.channels import ChannelLayout
from samplecore.models.experiment import Experiment, Reading
from samplecore.models.sample import Sample
from samplecore.models.sample_file import SampleFile
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.playback_rate import PostgresSamplePlaybackRateRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.sample_audio import SampleAudio

NOMINAL = Hearing(reading=Reading.NOMINAL, playback_rate_by_hash={})
SAMPLE_FRAMES = 32


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


def _extract(
    connection: Connection,
    library_root: Path,
    experiment_id: int,
    *,
    extractor: FeatureExtractor | None = None,
    hearing: Hearing = NOMINAL,
    sample_limit: int | None = None,
) -> FeatureExtractionSummary:
    feature_pass = FeaturePass(
        experiment_id=experiment_id,
        feature_extractor=extractor if extractor is not None else _StubFeatureExtractor(),
        hearing=hearing,
    )
    pending = pending_samples(connection, experiment_id, hearing=hearing, sample_limit=sample_limit)
    return extract_features(connection, SampleAudio.from_catalog(connection, library_root), feature_pass, pending)


def test_extract_features_writes_a_vector_for_every_cataloged_sample(connection: Connection, tmp_path: Path) -> None:
    first = _store_sample(connection, tmp_path, hash_seed=1)
    second = _store_sample(connection, tmp_path, hash_seed=2)
    experiment_id = _create_experiment(connection)

    summary = _extract(connection, tmp_path, experiment_id)

    assert summary == FeatureExtractionSummary(cataloged=2, already_extracted=0, newly_extracted=2, unavailable=0)
    vectors = PostgresSampleFeatureVectorRepository(connection).list_for_experiment(experiment_id)
    assert {vector.sample_hash for vector in vectors} == {first.hash, second.hash}


def test_a_second_run_skips_already_extracted_samples(connection: Connection, tmp_path: Path) -> None:
    _store_sample(connection, tmp_path, hash_seed=1)
    experiment_id = _create_experiment(connection)
    _extract(connection, tmp_path, experiment_id)
    _store_sample(connection, tmp_path, hash_seed=2)

    summary = _extract(connection, tmp_path, experiment_id)

    assert summary == FeatureExtractionSummary(cataloged=2, already_extracted=1, newly_extracted=1, unavailable=0)


def test_a_different_experiment_extracts_independently(connection: Connection, tmp_path: Path) -> None:
    _store_sample(connection, tmp_path, hash_seed=1)
    first_experiment_id = _create_experiment(connection)
    _extract(connection, tmp_path, first_experiment_id)

    second_experiment_id = _create_experiment(connection)
    summary = _extract(connection, tmp_path, second_experiment_id)

    assert summary == FeatureExtractionSummary(cataloged=1, already_extracted=0, newly_extracted=1, unavailable=0)


def test_sample_limit_bounds_how_many_new_samples_are_extracted(connection: Connection, tmp_path: Path) -> None:
    _store_sample(connection, tmp_path, hash_seed=1)
    _store_sample(connection, tmp_path, hash_seed=2)
    experiment_id = _create_experiment(connection)

    summary = _extract(connection, tmp_path, experiment_id, sample_limit=1)

    assert summary.newly_extracted == 1


def test_a_heard_rate_reading_hands_the_extractor_the_frames_as_the_library_plays_them(
    connection: Connection, tmp_path: Path
) -> None:
    """A sample played at half the stored rate lasts twice as long, and one no pattern plays keeps its frames."""
    played = _store_sample(connection, tmp_path, hash_seed=1)
    silent = _store_sample(connection, tmp_path, hash_seed=2)
    PostgresSamplePlaybackRateRepository(connection).replace_all({played.hash: NOMINAL_WAV_RATE // 2})
    experiment_id = _create_experiment(connection)

    _extract(connection, tmp_path, experiment_id, hearing=hearing_for(connection, Reading.HEARD_RATE))

    frames_by_hash = {
        vector.sample_hash: vector.vector[0]
        for vector in PostgresSampleFeatureVectorRepository(connection).list_for_experiment(experiment_id)
    }
    assert frames_by_hash == {played.hash: 2 * SAMPLE_FRAMES, silent.hash: SAMPLE_FRAMES}


def test_pending_samples_lists_only_what_the_experiment_lacks_in_hash_order(
    connection: Connection, tmp_path: Path
) -> None:
    for hash_seed in (3, 1, 2):
        _store_sample(connection, tmp_path, hash_seed=hash_seed)
    experiment_id = _create_experiment(connection)
    _extract(connection, tmp_path, experiment_id, sample_limit=1)

    pending = pending_samples(connection, experiment_id, hearing=NOMINAL, sample_limit=None)

    assert (pending.cataloged, pending.already_extracted) == (3, 1)
    assert [sample.hash for sample in pending.samples] == [format(2, "064x"), format(3, "064x")]


def test_a_sample_limit_below_one_is_refused(connection: Connection) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        pending_samples(connection, _create_experiment(connection), hearing=NOMINAL, sample_limit=0)


def test_an_empty_catalog_extracts_nothing(connection: Connection, tmp_path: Path) -> None:
    experiment_id = _create_experiment(connection)

    summary = _extract(connection, tmp_path, experiment_id)

    assert summary == FeatureExtractionSummary(cataloged=0, already_extracted=0, newly_extracted=0, unavailable=0)


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
        _extract(connection, tmp_path, experiment_id, extractor=_InterruptingFeatureExtractor())

    vectors = PostgresSampleFeatureVectorRepository(connection).list_for_experiment(experiment_id)
    assert len(vectors) == 2


def test_a_sample_whose_file_is_gone_is_counted_and_stays_pending(
    connection: Connection, tmp_path: Path, vanished_sample_file: SampleFile
) -> None:
    _store_sample(connection, tmp_path, hash_seed=1)
    experiment_id = _create_experiment(connection)

    summary = _extract(connection, tmp_path, experiment_id)

    assert (summary.newly_extracted, summary.unavailable) == (1, 1)
    still_pending = pending_samples(connection, experiment_id, hearing=NOMINAL, sample_limit=None).samples
    assert [pending.hash for pending in still_pending] == [vanished_sample_file.sample_hash]


def test_a_sample_the_library_plays_at_another_rate_now_is_described_again_in_place(
    connection: Connection, tmp_path: Path
) -> None:
    """A new module playing a sample, or a file declaring another rate, moves its heard rate, and its vector follows."""
    played = _store_sample(connection, tmp_path, hash_seed=1)
    steady = _store_sample(connection, tmp_path, hash_seed=2)
    rates = PostgresSamplePlaybackRateRepository(connection)
    rates.replace_all({played.hash: NOMINAL_WAV_RATE // 2, steady.hash: NOMINAL_WAV_RATE})
    experiment_id = _create_experiment(connection)
    _extract(connection, tmp_path, experiment_id, hearing=hearing_for(connection, Reading.HEARD_RATE))
    assert (
        pending_samples(
            connection, experiment_id, hearing=hearing_for(connection, Reading.HEARD_RATE), sample_limit=None
        ).samples
        == ()
    )

    rates.replace_all({played.hash: NOMINAL_WAV_RATE // 4, steady.hash: NOMINAL_WAV_RATE})
    moved_hearing = hearing_for(connection, Reading.HEARD_RATE)
    pending = pending_samples(connection, experiment_id, hearing=moved_hearing, sample_limit=None)
    summary = _extract(connection, tmp_path, experiment_id, hearing=moved_hearing)

    assert [sample.hash for sample in pending.samples] == [played.hash]
    assert pending.moved == frozenset({played.hash})
    assert summary == FeatureExtractionSummary(cataloged=2, already_extracted=1, newly_extracted=1, unavailable=0)
    vectors = {
        vector.sample_hash: vector
        for vector in PostgresSampleFeatureVectorRepository(connection).list_for_experiment(experiment_id)
    }
    assert {sample_hash: vector.heard_rate for sample_hash, vector in vectors.items()} == {
        played.hash: NOMINAL_WAV_RATE // 4,
        steady.hash: NOMINAL_WAV_RATE,
    }
    assert vectors[played.hash].vector[0] == 4 * SAMPLE_FRAMES


def test_a_nominal_reading_records_no_rate_and_ignores_the_library_s_rates(
    connection: Connection, tmp_path: Path
) -> None:
    sample = _store_sample(connection, tmp_path, hash_seed=1)
    experiment_id = _create_experiment(connection)
    _extract(connection, tmp_path, experiment_id)

    PostgresSamplePlaybackRateRepository(connection).replace_all({sample.hash: NOMINAL_WAV_RATE // 2})

    assert pending_samples(connection, experiment_id, hearing=NOMINAL, sample_limit=None).samples == ()
    (vector,) = PostgresSampleFeatureVectorRepository(connection).list_for_experiment(experiment_id)
    assert vector.heard_rate is None
