from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

import numpy as np
import umap
from sqlalchemy import Connection

from samplecloud.standardization import standardize
from samplecore.models.cloud import SampleCloudCoordinate
from samplecore.models.spectral import SampleSpectralFeature
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.cloud import CloudCoordinateRepository, PostgresCloudCoordinateRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.spectral import (
    PostgresSampleSpectralFeatureRepository,
    SampleSpectralFeatureRepository,
)

DEFAULT_N_NEIGHBORS: Final[int] = 15
MINIMUM_SAMPLES_FOR_REDUCTION: Final[int] = 2
RANDOM_SEED: Final[int] = 0
DISTANCE_METRIC: Final[str] = "euclidean"

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CloudSummary:
    """What one coordinate-reduction pass did, across one experiment's feature vectors."""

    samples_reduced: int


def reduce_and_persist_coordinates(connection: Connection, experiment_id: int) -> CloudSummary:
    """Fit UMAP over one experiment's feature vectors and persist a 2D coordinate for each sample.

    A full recompute every run, rather than placing only new points into an already-fitted model,
    is a deliberate simplification: UMAP has no natural per-point incremental update without
    persisting and versioning a fitted model, and a full fit is cheap enough at a personal
    library's scale not to need that complexity yet. The whole pass runs as one transaction,
    mirroring ``detect_equivalences``'s crash-safety pattern -- a recompute either lands
    completely or not at all. Each sample's standardized feature vector -- the same one the
    projection below is fit from -- is persisted alongside its coordinate, so a named, reusable
    "spectral distance" between two samples is always the same metric this projection respects.

    ``sample_feature_vector.sample_hash`` foreign-keys to ``sample.hash``, so every vector this
    reads already belongs to a cataloged sample -- promoting an experiment can never reference a
    sample the catalog no longer has.
    """
    feature_vectors = PostgresSampleFeatureVectorRepository(connection).list_for_experiment(experiment_id)
    if len(feature_vectors) < MINIMUM_SAMPLES_FOR_REDUCTION:
        return CloudSummary(samples_reduced=0)

    sample_hashes = [vector.sample_hash for vector in feature_vectors]
    feature_matrix = np.stack([np.array(vector.vector, dtype=np.float64) for vector in feature_vectors])
    standardized = standardize(feature_matrix)
    n_neighbors = min(DEFAULT_N_NEIGHBORS, len(sample_hashes) - 1)
    _logger.info("Fitting UMAP over %d feature vectors...", len(sample_hashes))
    coordinates = umap.UMAP(
        n_neighbors=n_neighbors, metric=DISTANCE_METRIC, random_state=RANDOM_SEED, verbose=True
    ).fit_transform(standardized)
    _logger.info("UMAP fit complete.")

    coordinate_repository: CloudCoordinateRepository = PostgresCloudCoordinateRepository(connection)
    spectral_feature_repository: SampleSpectralFeatureRepository = PostgresSampleSpectralFeatureRepository(connection)
    computed_at = datetime.now(UTC)
    new_coordinates: list[SampleCloudCoordinate] = []
    new_features: list[SampleSpectralFeature] = []
    for sample_hash, (x, y), vector in zip(sample_hashes, coordinates, standardized, strict=True):
        new_coordinates.append(
            SampleCloudCoordinate(sample_hash=sample_hash, x=float(x), y=float(y), computed_at=computed_at)
        )
        new_features.append(
            SampleSpectralFeature(
                sample_hash=sample_hash, vector=tuple(float(value) for value in vector), computed_at=computed_at
            )
        )

    _logger.info("Persisting %d coordinates and spectral vectors...", len(sample_hashes))
    with start_batch(connection):
        coordinate_repository.replace_all(new_coordinates)
        spectral_feature_repository.replace_all(new_features)
    _logger.info("Persisting complete.")

    return CloudSummary(samples_reduced=len(sample_hashes))
