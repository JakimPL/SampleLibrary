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
    """One extraction's parts: whose experiment it fills, what hears a sample, how, and over how many.

    ``sample_limit``, when given, bounds how many new samples the pass extracts, for validating a
    run over a small slice before committing to the whole catalog. ``hearing`` says how each
    sample's frames reach the extractor: at the stored rate, or as the library plays them.
    """

    experiment_id: int
    feature_extractor: FeatureExtractor
    hearing: Hearing
    sample_limit: int | None


def extract_features(connection: Connection, library_root: Path, feature_pass: FeaturePass) -> FeatureExtractionSummary:
    """Extract a feature vector for every cataloged sample the pass's experiment does not have yet.

    Idempotent within one experiment: resuming an interrupted or previously limited run only
    extracts samples the experiment has no vector for yet, matching ``run_extraction``'s and
    ``detect_equivalences``'s own "skip what's already done" idempotence.

    Vectors are committed to the catalog every ``EXTRACTION_CHECKPOINT_INTERVAL`` samples, not only
    once at the end -- extraction is the slowest stage of an embedding run, so an interruption
    partway through a real library's pass loses at most one checkpoint's worth of work on restart,
    rather than the whole pass.
    """
    experiment_id = feature_pass.experiment_id
    samples = PostgresSampleRepository(connection).list_all()
    feature_vector_repository = PostgresSampleFeatureVectorRepository(connection)
    already_extracted_hashes = {
        vector.sample_hash for vector in feature_vector_repository.list_for_experiment(experiment_id)
    }
    missing = [sample for sample in samples if sample.hash not in already_extracted_hashes]
    if feature_pass.sample_limit is not None:
        missing = missing[: feature_pass.sample_limit]

    _logger.info("%d samples already extracted, %d to extract.", len(already_extracted_hashes), len(missing))

    pending_vectors: list[SampleFeatureVector] = []
    newly_extracted_count = 0
    for sample in tqdm(missing, desc="Extracting features"):
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
        cataloged=len(samples), already_extracted=len(already_extracted_hashes), newly_extracted=newly_extracted_count
    )
