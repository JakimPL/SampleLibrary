from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection
from tqdm import tqdm

from samplecloud.backends import FeatureExtractor
from samplecloud.feature_store import read_features, write_features
from samplecore.storage import audio_store
from samplecore.storage.repositories.sample import DuckDBSampleRepository

FEATURE_STORE_CHECKPOINT_INTERVAL: Final[int] = 500

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeatureExtractionSummary:
    """What one feature-extraction run did, across every sample it considered."""

    catalogued: int
    already_extracted: int
    newly_extracted: int


def extract_features(
    connection: Connection,
    library_root: Path,
    feature_store_path: Path,
    feature_extractor: FeatureExtractor,
    *,
    sample_limit: int | None = None,
) -> FeatureExtractionSummary:
    """Extract a feature vector for every catalogued sample the store does not already have.

    Idempotent: rerunning after a previous pass only extracts samples added to the catalog since,
    matching ``run_extraction``'s and ``detect_equivalences``'s own "skip what's already done"
    idempotence. ``sample_limit``, when given, bounds how many new samples this run extracts, for
    validating a run over a small slice before committing to the whole catalog.

    The store is checkpointed to disk every ``FEATURE_STORE_CHECKPOINT_INTERVAL`` samples, not
    only once at the end -- extraction is the slowest stage of an embedding run, so an
    interruption partway through a real library's pass loses at most one checkpoint's worth of
    work on restart, rather than the whole pass.
    """
    samples = DuckDBSampleRepository(connection).list_all()
    existing = read_features(feature_store_path)
    missing = [sample for sample in samples if sample.hash not in existing]
    if sample_limit is not None:
        missing = missing[:sample_limit]

    _logger.info("%d samples already extracted, %d to extract.", len(existing), len(missing))

    newly_extracted: dict[str, NDArray[np.float64]] = {}
    for sample in tqdm(missing, desc="Extracting features"):
        newly_extracted[sample.hash] = feature_extractor.extract(audio_store.read(library_root, sample).pcm)
        if len(newly_extracted) % FEATURE_STORE_CHECKPOINT_INTERVAL == 0:
            write_features(feature_store_path, {**existing, **newly_extracted})

    write_features(feature_store_path, {**existing, **newly_extracted})
    _logger.info("Feature extraction complete.")
    return FeatureExtractionSummary(
        catalogued=len(samples), already_extracted=len(existing), newly_extracted=len(newly_extracted)
    )
