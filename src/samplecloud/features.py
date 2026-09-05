from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
from tqdm import tqdm

from samplecloud.backends import FeatureExtractor
from samplecloud.feature_store import read_features, write_features
from samplecore.storage import audio_store
from samplecore.storage.repositories.sample import DuckDBSampleRepository


@dataclass(frozen=True)
class FeatureExtractionSummary:
    """What one feature-extraction run did, across every sample it considered."""

    catalogued: int
    already_extracted: int
    newly_extracted: int


def extract_features(
    connection: duckdb.DuckDBPyConnection,
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
    """
    samples = DuckDBSampleRepository(connection).list_all()
    existing = read_features(feature_store_path)
    missing = [sample for sample in samples if sample.hash not in existing]
    if sample_limit is not None:
        missing = missing[:sample_limit]

    newly_extracted = {
        sample.hash: feature_extractor.extract(audio_store.read(library_root, sample).pcm)
        for sample in tqdm(missing, desc="Extracting features")
    }

    write_features(feature_store_path, {**existing, **newly_extracted})
    return FeatureExtractionSummary(
        catalogued=len(samples), already_extracted=len(existing), newly_extracted=len(newly_extracted)
    )
