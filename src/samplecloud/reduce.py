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
from samplecore.storage.repositories.sample import DuckDBSampleRepository
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
    """What one coordinate-reduction pass did, across every feature vector it considered.

    ``samples_orphaned`` counts feature-store entries for a sample hash no longer in the catalog --
    left behind by a reset whose cache predates it, or by any other drift between the store and the
    catalog -- skipped rather than reduced, since a coordinate can never reference a sample that no
    longer exists.
    """

    samples_reduced: int
    samples_orphaned: int


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

    The feature store is a standalone cache, keyed only by sample hash, so it can outlive the
    catalog row it was computed from -- a reset that clears the catalog but predates a fix to also
    clear this cache, or any other drift between the two, would otherwise leave a stale entry that
    a coordinate upsert can never satisfy, since ``sample_cloud_coordinates`` and
    ``sample_spectral_feature`` both foreign-key to ``sample``. Filtering to hashes the catalog
    still recognizes keeps every fit and every persisted row honestly scoped to the library as it
    exists today.
    """
    features = read_features(feature_store_path)
    catalogued_hashes = {sample_.hash for sample_ in DuckDBSampleRepository(connection).list_all()}
    orphaned_hash_count = sum(1 for sample_hash in features if sample_hash not in catalogued_hashes)
    features = {sample_hash: vector for sample_hash, vector in features.items() if sample_hash in catalogued_hashes}
    if len(features) < MINIMUM_SAMPLES_FOR_REDUCTION:
        return CloudSummary(samples_reduced=0, samples_orphaned=orphaned_hash_count)

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

    return CloudSummary(samples_reduced=len(sample_hashes), samples_orphaned=orphaned_hash_count)
