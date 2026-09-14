from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from sqlalchemy import Connection, delete
from trackmod.core.samples.depth import BitDepth

from samplecloud.backends import FeatureExtractor
from samplecloud.evaluation.corpus import load_corpus
from samplecloud.evaluation.settings import EvaluationSettings
from samplecloud.evaluation.transposition import ProbeDescriber, TranspositionRetrieval, transposition_retrieval
from samplecloud.hearing import Hearing, hearing_for
from samplecore.models.channels import ChannelLayout
from samplecore.models.experiment import Experiment, Reading, SampleFeatureVector
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplecore.storage.database import sample, sample_feature_vector
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.playback_rate import PostgresSamplePlaybackRateRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository

SHORTEST_FRAME_COUNT = 2000
FRAME_STEP = 400
SAMPLE_COUNT = 12
SETTINGS = EvaluationSettings(random_seed=0, probe_count=6, semitone_offsets=(-7.0, 7.0))
NOMINAL = Hearing(reading=Reading.NOMINAL, playback_rate_by_hash={})


class LoudnessShapeExtractor:
    """Describes how a waveform's level is shaped over time, which a retuning leaves alone.

    Reading the envelope at a fixed number of points, rather than per frame, is what makes it hold:
    playing the same waveform faster shortens it without changing the shape those points trace.
    """

    def extract(self, waveform: NDArray[np.float64]) -> NDArray[np.float64]:
        mono = np.abs(waveform.mean(axis=1) if waveform.ndim > 1 else waveform)
        points = np.array_split(mono, 8)
        envelope = np.array([float(np.sqrt(np.mean(point**2))) for point in points])
        peak = float(envelope.max())
        return envelope / peak if peak > 0.0 else envelope


class DurationExtractor:
    """Describes a waveform by how long it is, which a retuning changes by construction."""

    def extract(self, waveform: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.array([float(waveform.shape[0]), float(waveform.shape[0]) ** 0.5])


def _tone(frames: int, *, frequency: float, decay: float) -> NDArray[np.float64]:
    positions = np.arange(frames, dtype=np.float64)
    wave = np.sin(2.0 * np.pi * frequency * positions / 44100.0) * np.exp(-decay * positions / frames)
    return wave.reshape(-1, 1)


def _seed(
    connection: Connection, library_root: Path, extractor: FeatureExtractor, *, heard_rate: int | None = None
) -> int:
    """Store the samples, then the vectors the extractor draws from each as the experiment hears it.

    A `heard_rate` is recorded as the rate every sample is played at, and the vectors are drawn
    from the samples heard at it.
    """
    experiment_repository = PostgresExperimentRepository(connection)
    experiment_id = experiment_repository.next_id()
    experiment_repository.insert(
        Experiment(id=experiment_id, backend_name="stub", params={}, created_at=datetime.now(UTC), label=None)
    )
    sample_repository = PostgresSampleRepository(connection)
    waveforms: dict[str, NDArray[np.float64]] = {}
    for index in range(SAMPLE_COUNT):
        frames = SHORTEST_FRAME_COUNT + index * FRAME_STEP
        sample = Sample(
            hash=format(index + 1, "064x"), depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=frames
        )
        sample_repository.upsert(sample)
        waveforms[sample.hash] = _tone(frames, frequency=110.0 * (1.0 + index / 3.0), decay=1.0 + index)
        audio_store.write(library_root, SamplePCM(sample=sample, pcm=waveforms[sample.hash]))
    if heard_rate is not None:
        PostgresSamplePlaybackRateRepository(connection).replace_all(dict.fromkeys(waveforms, heard_rate))
    hearing = hearing_for(connection, Reading.NOMINAL if heard_rate is None else Reading.HEARD_RATE)
    PostgresSampleFeatureVectorRepository(connection).insert_many(
        [
            SampleFeatureVector(
                experiment_id=experiment_id,
                sample_hash=sample_hash,
                vector=tuple(extractor.extract(hearing.hear(sample_hash, waveform)).tolist()),
                computed_at=datetime.now(UTC),
            )
            for sample_hash, waveform in waveforms.items()
        ]
    )
    connection.commit()
    return experiment_id


def _retrieve(
    connection: Connection,
    library_root: Path,
    experiment_id: int,
    extractor: FeatureExtractor,
    *,
    hearing: Hearing = NOMINAL,
    settings: EvaluationSettings = SETTINGS,
) -> TranspositionRetrieval:
    corpus = load_corpus(connection, experiment_id=experiment_id)
    retrieval = transposition_retrieval(
        connection,
        corpus,
        library_root=library_root,
        describer=ProbeDescriber(feature_extractor=extractor, hearing=hearing),
        settings=settings,
    )
    assert retrieval is not None
    return retrieval


def test_a_descriptor_a_retuning_leaves_alone_finds_the_original_again(connection: Connection, tmp_path: Path) -> None:
    """The property the whole representation is built for, measurable without any label."""
    extractor = LoudnessShapeExtractor()
    experiment_id = _seed(connection, tmp_path, extractor)

    retrieval = _retrieve(connection, tmp_path, experiment_id, extractor)

    assert retrieval.rank_one_share > 0.5
    assert retrieval.median_rank == pytest.approx(1.0)


def test_a_descriptor_a_retuning_moves_loses_the_original(connection: Connection, tmp_path: Path) -> None:
    """Reading duration alone lands a retuned sample on whichever sample is that long instead.

    The samples run from short to long in even steps, so playing one faster puts it at the length
    another already occupies -- which is what a descriptor built on pitch does across a catalog.
    """
    extractor = DurationExtractor()
    experiment_id = _seed(connection, tmp_path, extractor)

    retrieval = _retrieve(connection, tmp_path, experiment_id, extractor)

    assert retrieval.rank_one_share < 0.5


def test_retrieval_runs_one_trial_per_probe_and_offset(connection: Connection, tmp_path: Path) -> None:
    extractor = LoudnessShapeExtractor()
    experiment_id = _seed(connection, tmp_path, extractor)

    retrieval = _retrieve(connection, tmp_path, experiment_id, extractor)

    assert len(retrieval.offsets) == len(SETTINGS.semitone_offsets)
    assert all(offset.trial_count == SETTINGS.probe_count for offset in retrieval.offsets)
    assert retrieval.probe_sample_count == SETTINGS.probe_count
    assert retrieval.catalog_sample_count == SAMPLE_COUNT


def test_two_retrieval_passes_draw_the_same_probes(connection: Connection, tmp_path: Path) -> None:
    extractor = LoudnessShapeExtractor()
    experiment_id = _seed(connection, tmp_path, extractor)

    first = _retrieve(connection, tmp_path, experiment_id, extractor)
    second = _retrieve(connection, tmp_path, experiment_id, extractor)

    assert first == second


def test_probes_are_heard_the_way_the_experiment_heard_its_samples(connection: Connection, tmp_path: Path) -> None:
    """Unretuned, a probe heard at the experiment's own reading is described exactly as its stored vector."""
    extractor = DurationExtractor()
    experiment_id = _seed(connection, tmp_path, extractor, heard_rate=NOMINAL_WAV_RATE // 2)
    unretuned = EvaluationSettings(random_seed=0, probe_count=6, semitone_offsets=(0.0,))

    heard = _retrieve(
        connection,
        tmp_path,
        experiment_id,
        extractor,
        hearing=hearing_for(connection, Reading.HEARD_RATE),
        settings=unretuned,
    )
    nominal = _retrieve(connection, tmp_path, experiment_id, extractor, settings=unretuned)

    assert heard.rank_one_share == pytest.approx(1.0)
    assert nominal.rank_one_share < heard.rank_one_share


def test_a_corpus_whose_probes_left_the_catalog_retrieves_nothing(connection: Connection, tmp_path: Path) -> None:
    extractor = LoudnessShapeExtractor()
    experiment_id = _seed(connection, tmp_path, extractor)
    corpus = load_corpus(connection, experiment_id=experiment_id)
    connection.execute(delete(sample_feature_vector))
    connection.execute(delete(sample))
    connection.commit()

    retrieval = transposition_retrieval(
        connection,
        corpus,
        library_root=tmp_path,
        describer=ProbeDescriber(feature_extractor=extractor, hearing=NOMINAL),
        settings=SETTINGS,
    )

    assert retrieval is None
