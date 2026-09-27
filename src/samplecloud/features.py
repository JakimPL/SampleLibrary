from __future__ import annotations

import logging
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from typing import Final

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection

from samplecloud.backends import FeatureExtractor
from samplecloud.hearing import Hearing
from samplecore.models.experiment import SampleFeatureVector
from samplecore.models.sample import Sample
from samplecore.prefetch import prefetched
from samplecore.progress import ProgressBar
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.sample_audio import SampleAudio, SampleUnavailableError, readable_sample_hashes

EXTRACTION_CHECKPOINT_INTERVAL: Final[int] = 500
EXTRACTION_BATCH_SIZE: Final[int] = 16
READ_AHEAD_SAMPLES: Final[int] = 64
EXTRACTION_LABEL: Final[str] = "Extracting features"

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeatureExtractionSummary:
    """What one feature-extraction run did, across every sample it considered.

    ``unavailable`` counts the pending samples whose audio lives only in sample files none of which
    holds it now; they stay pending, so a later run describes them once a file is back.
    """

    cataloged: int
    already_extracted: int
    newly_extracted: int
    unavailable: int


@dataclass(frozen=True)
class FeaturePass:
    """One extraction's parts: whose experiment it fills, and what hears a sample and how.

    ``hearing`` says how each sample's frames reach the extractor: at the stored rate, or as the
    library plays them.
    """

    experiment_id: int
    feature_extractor: FeatureExtractor
    hearing: Hearing


@dataclass(frozen=True)
class PendingSamples:
    """The cataloged samples an experiment still has to describe, in hash order, and what it holds that stands.

    ``moved`` names the samples it holds a vector for that was heard at a rate the library no longer
    plays them at; they are pending too, and their vectors are replaced as they are described again.
    """

    cataloged: int
    already_extracted: int
    samples: tuple[Sample, ...]
    moved: frozenset[str]


def pending_samples(
    connection: Connection, experiment_id: int, *, hearing: Hearing, sample_limit: int | None
) -> PendingSamples:
    """The samples a pass over one experiment still has to describe, the first ``sample_limit`` of them when given.

    Read before any extractor is built, so a pass with nothing left to describe loads no model. A
    sample is pending when the experiment holds no vector for it, or holds one heard at another rate
    than ``hearing`` hears it at now, which a new module playing the sample, or a sample file
    declaring another rate, brings about. ``sample_limit`` bounds a pass for validating a run over a
    small slice; the same slice comes first every run, since samples arrive in hash order.

    Raises:
        ValueError: ``sample_limit`` is below one.
    """
    if sample_limit is not None and sample_limit < 1:
        raise ValueError(f"a sample limit counts samples to describe, so it is at least 1, got {sample_limit}")

    samples = PostgresSampleRepository(connection).list_all()
    held = PostgresSampleFeatureVectorRepository(connection).heard_rates_for_experiment(experiment_id)
    moved = frozenset(sample_hash for sample_hash, rate in held.items() if rate != hearing.rate_for(sample_hash))
    missing = tuple(sample for sample in samples if sample.hash not in held or sample.hash in moved)
    return PendingSamples(
        cataloged=len(samples),
        already_extracted=len(held) - len(moved),
        samples=missing if sample_limit is None else missing[:sample_limit],
        moved=moved,
    )


def readable_pending_count(connection: Connection, experiment_id: int, *, hearing: Hearing) -> int:
    """How many samples whose audio can be read now an experiment still has to describe, read without any audio.

    The pending rule is `pending_samples`' own, over the samples a pass can reach: a sample whose
    only file is gone stays out of the count until the file is back, so an experiment describing
    everything readable counts nothing left.
    """
    held = PostgresSampleFeatureVectorRepository(connection).heard_rates_for_experiment(experiment_id)
    return sum(
        1
        for sample_hash in readable_sample_hashes(connection)
        if sample_hash not in held or held[sample_hash] != hearing.rate_for(sample_hash)
    )


def extract_features(
    connection: Connection, audio: SampleAudio, feature_pass: FeaturePass, pending: PendingSamples, *, batch_size: int
) -> FeatureExtractionSummary:
    """Extract a feature vector for every pending sample of the pass's experiment.

    Idempotent within one experiment: resuming an interrupted or previously limited run only
    extracts samples the experiment has no vector for yet (see ``pending_samples``), matching
    ``run_extraction``'s and ``detect_equivalences``'s own "skip what's already done" idempotence.

    Vectors are committed to the catalog every ``EXTRACTION_CHECKPOINT_INTERVAL`` samples, not only
    once at the end -- extraction is the slowest stage of an embedding run, so an interruption
    partway through a real library's pass loses at most one checkpoint's worth of work on restart,
    rather than the whole pass. A moved sample's old vector leaves in the checkpoint that stores its
    new one, so the experiment holds one vector per sample throughout.

    Samples are described ``batch_size`` at a time, which an extractor reading a batch in one pass
    answers faster, while a thread reads and hears the ones after them. A batch ends at a checkpoint,
    so every checkpoint holds exactly the samples described before it.
    """
    _logger.info("%d samples already extracted, %d to extract.", pending.already_extracted, len(pending.samples))
    read_ahead = prefetched(pending.samples, partial(_heard, audio, feature_pass.hearing), depth=READ_AHEAD_SAMPLES)
    with (
        closing(read_ahead) as heard_samples,
        ProgressBar(total=len(pending.samples), label=EXTRACTION_LABEL) as progress,
    ):
        extraction = _Extraction(connection, feature_pass, pending, batch_size=batch_size, progress=progress)
        for sample, heard in heard_samples:
            extraction.take(sample, heard)
        extraction.finish()
    _logger.info("Feature extraction complete.")
    return FeatureExtractionSummary(
        cataloged=pending.cataloged,
        already_extracted=pending.already_extracted,
        newly_extracted=extraction.newly_extracted,
        unavailable=extraction.unavailable,
    )


def _heard(audio: SampleAudio, hearing: Hearing, sample: Sample) -> NDArray[np.float64] | None:
    """The sample's frames as the pass hears them, or None where no file holds the sample now."""
    try:
        sample_pcm = audio.read(sample)
    except SampleUnavailableError:
        return None
    return hearing.hear(sample.hash, sample_pcm.pcm)


class _Extraction:
    """One pass through its pending samples: the batch it gathers, and the checkpoint the described batches fill."""

    def __init__(
        self,
        connection: Connection,
        feature_pass: FeaturePass,
        pending: PendingSamples,
        *,
        batch_size: int,
        progress: ProgressBar,
    ) -> None:
        self._connection = connection
        self._feature_pass = feature_pass
        self._moved = pending.moved
        self._batch_size = batch_size
        self._progress = progress
        self._repository = PostgresSampleFeatureVectorRepository(connection)
        self._batch: list[tuple[Sample, NDArray[np.float64]]] = []
        self._checkpoint: list[SampleFeatureVector] = []
        self.newly_extracted = 0
        self.unavailable = 0

    def take(self, sample: Sample, heard: NDArray[np.float64] | None) -> None:
        """Add one sample to the batch, describing the batch once it is full or reaches the next checkpoint."""
        if heard is None:
            self.unavailable += 1
            self._progress.update(1)
            return
        self._batch.append((sample, heard))
        room = EXTRACTION_CHECKPOINT_INTERVAL - len(self._checkpoint)
        if len(self._batch) >= min(self._batch_size, room):
            self._describe_batch()

    def finish(self) -> None:
        """Describe what the last batch holds, and commit the last checkpoint."""
        if self._batch:
            self._describe_batch()
        self._store()

    def _describe_batch(self) -> None:
        hearing = self._feature_pass.hearing
        vectors = self._feature_pass.feature_extractor.extract_many([heard for _, heard in self._batch])
        described_at = datetime.now(UTC)
        self._checkpoint.extend(
            SampleFeatureVector(
                experiment_id=self._feature_pass.experiment_id,
                sample_hash=sample.hash,
                vector=tuple(float(value) for value in vector),
                computed_at=described_at,
                heard_rate=hearing.rate_for(sample.hash),
            )
            for (sample, _), vector in zip(self._batch, vectors, strict=True)
        )
        self.newly_extracted += len(self._batch)
        self._progress.update(len(self._batch))
        self._batch = []
        if len(self._checkpoint) >= EXTRACTION_CHECKPOINT_INTERVAL:
            self._store()

    def _store(self) -> None:
        _store_checkpoint(
            self._connection,
            self._repository,
            self._checkpoint,
            experiment_id=self._feature_pass.experiment_id,
            moved=self._moved,
        )
        self._checkpoint = []


def _store_checkpoint(
    connection: Connection,
    repository: PostgresSampleFeatureVectorRepository,
    vectors: list[SampleFeatureVector],
    *,
    experiment_id: int,
    moved: frozenset[str],
) -> None:
    """Commit a checkpoint of vectors, replacing the ones a moved sample held."""
    repository.delete_for_samples(
        experiment_id, [vector.sample_hash for vector in vectors if vector.sample_hash in moved]
    )
    repository.insert_many(vectors)
    connection.commit()
