from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from sqlalchemy import Connection
from tqdm import tqdm

from samplecloud.backends import FeatureExtractor
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


def extract_features(
    connection: Connection,
    library_root: Path,
    experiment_id: int,
    feature_extractor: FeatureExtractor,
    *,
    sample_limit: int | None = None,
) -> FeatureExtractionSummary:
    """Extract a feature vector for every cataloged sample the given experiment does not have yet.

    Idempotent within one experiment: resuming an interrupted or previously limited run only
    extracts samples the experiment has no vector for yet, matching ``run_extraction``'s and
    ``detect_equivalences``'s own "skip what's already done" idempotence. ``sample_limit``, when
    given, bounds how many new samples this run extracts, for validating a run over a small slice
    before committing to the whole catalog.

    Vectors are committed to the catalog every ``EXTRACTION_CHECKPOINT_INTERVAL`` samples, not only
    once at the end -- extraction is the slowest stage of an embedding run, so an interruption
    partway through a real library's pass loses at most one checkpoint's worth of work on restart,
    rather than the whole pass.
    """
    samples = PostgresSampleRepository(connection).list_all()
    feature_vector_repository = PostgresSampleFeatureVectorRepository(connection)
    already_extracted_hashes = {
        vector.sample_hash for vector in feature_vector_repository.list_for_experiment(experiment_id)
    }
    missing = [sample for sample in samples if sample.hash not in already_extracted_hashes]
    if sample_limit is not None:
        missing = missing[:sample_limit]

    _logger.info("%d samples already extracted, %d to extract.", len(already_extracted_hashes), len(missing))

    pending_vectors: list[SampleFeatureVector] = []
    newly_extracted_count = 0
    for sample in tqdm(missing, desc="Extracting features"):
        raw_vector = feature_extractor.extract(audio_store.read(library_root, sample).pcm)
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
