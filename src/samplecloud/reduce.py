from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import numpy as np
import umap
from sklearn.preprocessing import StandardScaler
from sqlalchemy import Connection

from samplecloud.feature_store import read_features
from samplecore.models.cloud import SampleCloudCoordinate
from samplecore.models.spectral import SampleSpectralFeature
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.cloud import CloudCoordinateRepository, DuckDBCloudCoordinateRepository
from samplecore.storage.repositories.spectral import (
    DuckDBSampleSpectralFeatureRepository,
    SampleSpectralFeatureRepository,
)

DEFAULT_N_NEIGHBORS: Final[int] = 15
MINIMUM_SAMPLES_FOR_REDUCTION: Final[int] = 2
RANDOM_SEED: Final[int] = 0
DISTANCE_METRIC: Final[str] = "euclidean"


@dataclass(frozen=True)
class CloudSummary:
    """What one coordinate-reduction pass did, across every feature vector it considered."""

    samples_reduced: int


def reduce_and_persist_coordinates(connection: Connection, feature_store_path: Path) -> CloudSummary:
    """Fit UMAP over every currently-extracted feature vector and persist a 2D coordinate each.

    A full recompute every run, rather than placing only new points into an already-fitted model,
    is a deliberate simplification: UMAP has no natural per-point incremental update without
    persisting and versioning a fitted model, and a full fit is cheap enough at a personal
    library's scale not to need that complexity yet. The whole pass runs as one transaction,
    mirroring ``detect_equivalences``'s crash-safety pattern -- a recompute either lands
    completely or not at all. Each sample's standardized feature vector -- the same one the
    projection below is fit from -- is persisted alongside its coordinate, so a named, reusable
    "spectral distance" between two samples is always the same metric this projection respects.
    """
    features = read_features(feature_store_path)
    if len(features) < MINIMUM_SAMPLES_FOR_REDUCTION:
        return CloudSummary(samples_reduced=0)

    sample_hashes = list(features.keys())
    feature_matrix = np.stack([features[sample_hash] for sample_hash in sample_hashes])
    standardized = StandardScaler().fit_transform(feature_matrix)
    n_neighbors = min(DEFAULT_N_NEIGHBORS, len(sample_hashes) - 1)
    coordinates = umap.UMAP(n_neighbors=n_neighbors, metric=DISTANCE_METRIC, random_state=RANDOM_SEED).fit_transform(
        standardized
    )

    coordinate_repository: CloudCoordinateRepository = DuckDBCloudCoordinateRepository(connection)
    spectral_feature_repository: SampleSpectralFeatureRepository = DuckDBSampleSpectralFeatureRepository(connection)
    computed_at = datetime.now(UTC)
    with start_batch(connection):
        for sample_hash, (x, y), vector in zip(sample_hashes, coordinates, standardized, strict=True):
            coordinate_repository.upsert(
                SampleCloudCoordinate(sample_hash=sample_hash, x=float(x), y=float(y), computed_at=computed_at)
            )
            spectral_feature_repository.upsert(
                SampleSpectralFeature(
                    sample_hash=sample_hash,
                    vector=tuple(float(value) for value in vector),
                    computed_at=computed_at,
                )
            )

    return CloudSummary(samples_reduced=len(sample_hashes))
