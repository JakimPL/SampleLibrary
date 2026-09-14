from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from sqlalchemy import Connection
from tqdm import tqdm

from samplecloud.backends import FeatureExtractor
from samplecloud.hearing import Hearing
from samplecore.models.experiment import SampleFeatureVector
from samplecore.models.sample import Sample
from samplecore.storage import audio_store
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository

EXTRACTION_CHECKPOINT_INTERVAL: Final[int] = 500

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeatureExtractionSummary:
    """What one feature-extraction run did, across every sample it considered."""

    cataloged: int
    already_extracted: int
    newly_extracted: int


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
    """The cataloged samples an experiment holds no vector for yet, in hash order, and what it already holds."""

    cataloged: int
    already_extracted: int
    samples: tuple[Sample, ...]


def pending_samples(connection: Connection, experiment_id: int, *, sample_limit: int | None) -> PendingSamples:
    """The samples a pass over one experiment still has to describe, the first ``sample_limit`` of them when given.

    Read before any extractor is built, so a pass with nothing left to describe loads no model.
    ``sample_limit`` bounds a pass for validating a run over a small slice; the same slice comes
    first every run, since samples arrive in hash order.

    Raises:
        ValueError: ``sample_limit`` is below one.
    """
    if sample_limit is not None and sample_limit < 1:
        raise ValueError(f"a sample limit counts samples to describe, so it is at least 1, got {sample_limit}")

    samples = PostgresSampleRepository(connection).list_all()
    already = PostgresSampleFeatureVectorRepository(connection).sample_hashes_for_experiment(experiment_id)
    missing = tuple(sample for sample in samples if sample.hash not in already)
    return PendingSamples(
        cataloged=len(samples),
        already_extracted=len(already),
        samples=missing if sample_limit is None else missing[:sample_limit],
    )


def extract_features(
    connection: Connection, library_root: Path, feature_pass: FeaturePass, pending: PendingSamples
) -> FeatureExtractionSummary:
    """Extract a feature vector for every pending sample of the pass's experiment.

    Idempotent within one experiment: resuming an interrupted or previously limited run only
    extracts samples the experiment has no vector for yet (see ``pending_samples``), matching
    ``run_extraction``'s and ``detect_equivalences``'s own "skip what's already done" idempotence.

    Vectors are committed to the catalog every ``EXTRACTION_CHECKPOINT_INTERVAL`` samples, not only
    once at the end -- extraction is the slowest stage of an embedding run, so an interruption
    partway through a real library's pass loses at most one checkpoint's worth of work on restart,
    rather than the whole pass.
    """
    experiment_id = feature_pass.experiment_id
    feature_vector_repository = PostgresSampleFeatureVectorRepository(connection)
    _logger.info("%d samples already extracted, %d to extract.", pending.already_extracted, len(pending.samples))

    pending_vectors: list[SampleFeatureVector] = []
    newly_extracted_count = 0
    for sample in tqdm(pending.samples, desc="Extracting features"):
        heard = feature_pass.hearing.hear(sample.hash, audio_store.read(library_root, sample).pcm)
        raw_vector = feature_pass.feature_extractor.extract(heard)
        pending_vectors.append(
            SampleFeatureVector(
                experiment_id=experiment_id,
                sample_hash=sample.hash,
                vector=tuple(float(value) for value in raw_vector),
                computed_at=datetime.now(UTC),
            )
        )
        newly_extracted_count += 1
        if len(pending_vectors) >= EXTRACTION_CHECKPOINT_INTERVAL:
            feature_vector_repository.insert_many(pending_vectors)
            connection.commit()
            pending_vectors = []

    feature_vector_repository.insert_many(pending_vectors)
    connection.commit()
    _logger.info("Feature extraction complete.")
    return FeatureExtractionSummary(
        cataloged=pending.cataloged, already_extracted=pending.already_extracted, newly_extracted=newly_extracted_count
    )
