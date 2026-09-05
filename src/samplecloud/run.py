from __future__ import annotations

from dataclasses import dataclass

import duckdb

from samplecloud.backends import FeatureExtractor
from samplecloud.features import FeatureExtractionSummary, extract_features
from samplecloud.reduce import CloudSummary, reduce_and_persist_coordinates
from samplecore.config import LibraryConfig


@dataclass(frozen=True)
class EmbeddingSummary:
    """What one embedding run did, across both its extraction and reduction stages."""

    extraction: FeatureExtractionSummary
    reduction: CloudSummary


def run_embedding(
    config: LibraryConfig,
    connection: duckdb.DuckDBPyConnection,
    feature_extractor: FeatureExtractor,
    *,
    sample_limit: int | None = None,
) -> EmbeddingSummary:
    """Extract every missing sample's feature vector, then re-fit the whole library's 2D layout."""
    feature_store_path = config.resolved_cloud_artifact_directory / "features.parquet"
    extraction = extract_features(
        connection, config.library_root, feature_store_path, feature_extractor, sample_limit=sample_limit
    )
    reduction = reduce_and_persist_coordinates(connection, feature_store_path)
    return EmbeddingSummary(extraction=extraction, reduction=reduction)
