from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection

from samplecloud.stages import LayoutStages, NeighborGraph
from samplecloud.standardization import standardize
from samplecore.digests import digest_of_rows
from samplecore.models.cloud import CloudPromotion, SampleCloudCoordinate
from samplecore.models.spectral import SampleSpectralFeature
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.cloud import (
    CloudCoordinateRepository,
    PostgresCloudCoordinateRepository,
    PostgresCloudPromotionRepository,
)
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.spectral import (
    PostgresSampleSpectralFeatureRepository,
    SampleSpectralFeatureRepository,
)

DEFAULT_N_NEIGHBORS: Final[int] = 15
MINIMUM_SAMPLES_FOR_REDUCTION: Final[int] = 4
MINIMUM_N_NEIGHBORS: Final[int] = 2
RANDOM_SEED: Final[int] = 0
DISTANCE_METRIC: Final[str] = "euclidean"
# UMAP searches for neighbors exactly below this many points and approximately from it on.
APPROXIMATE_SEARCH_MINIMUM: Final[int] = 4096
# A seeded UMAP runs on one thread, which is what keeps its layout the same run after run.
SEEDED_JOBS: Final[int] = 1
MISSING_SEARCH_INDEX_WARNING: Final[str] = r"precomputed_knn\[2\]"
# The packages whose versions a layout depends on, so a new version lays out afresh.
LAYOUT_PACKAGES: Final[tuple[str, ...]] = ("umap-learn", "pynndescent")

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CloudSummary:
    """What one coordinate-reduction pass did, across one experiment's feature vectors."""

    samples_reduced: int


def neighbor_count(point_count: int) -> int:
    """How many neighbors a UMAP fit over ``point_count`` points weighs, bounded by the points it has."""
    return max(MINIMUM_N_NEIGHBORS, min(DEFAULT_N_NEIGHBORS, point_count - 1))


def fit_plane(standardized: NDArray[np.float64], *, n_neighbors: int, stages: LayoutStages) -> NDArray[np.float64]:
    """Lay standardized feature vectors out on a plane with UMAP: two coordinates per vector, in the order given.

    From `APPROXIMATE_SEARCH_MINIMUM` points on, where UMAP searches for neighbors approximately
    anyway, the neighbor graph is found first and kept among the layout's `stages`, and the fit reads
    it from there, so a fit stopped after the search starts again from the graph. The search and the
    fit each take their own draw of the seed, so the same vectors lay out the same way every time.
    """
    # UMAP compiles its kernels as it is imported, which a pass extracting features and laying out
    # nothing spares itself by importing it here.
    # pylint: disable=import-outside-toplevel
    import umap
    from sklearn.utils import check_random_state

    if standardized.shape[0] < APPROXIMATE_SEARCH_MINIMUM:
        small: NDArray[np.float64] = umap.UMAP(
            n_neighbors=n_neighbors, metric=DISTANCE_METRIC, random_state=RANDOM_SEED, verbose=True
        ).fit_transform(standardized)
        return small
    graph = stages.neighbors()
    if graph is None:
        indices, distances, _ = umap.umap_.nearest_neighbors(
            standardized,
            n_neighbors,
            DISTANCE_METRIC,
            {},
            False,
            check_random_state(RANDOM_SEED),
            low_memory=True,
            use_pynndescent=True,
            n_jobs=SEEDED_JOBS,
            verbose=True,
        )
        graph = NeighborGraph(indices=indices, distances=distances)
        stages.keep_neighbors(graph)
    with warnings.catch_warnings():
        # UMAP warns that a graph found apart from the fit carries no index for placing new points,
        # which the cloud never asks it to do.
        warnings.filterwarnings("ignore", message=MISSING_SEARCH_INDEX_WARNING, category=UserWarning)
        coordinates: NDArray[np.float64] = umap.UMAP(
            n_neighbors=n_neighbors,
            metric=DISTANCE_METRIC,
            random_state=RANDOM_SEED,
            verbose=True,
            precomputed_knn=(graph.indices, graph.distances),
        ).fit_transform(standardized)
    return coordinates


def layout_digest(experiment_id: int, *, membership: str, n_neighbors: int) -> str:
    """The name of the layout one experiment's vectors make: the vectors, how UMAP reads them, and which UMAP reads them."""
    return digest_of_rows(
        [
            (experiment_id, membership, n_neighbors, DISTANCE_METRIC, RANDOM_SEED),
            *((package, version(package)) for package in LAYOUT_PACKAGES),
        ]
    )


def reduce_and_persist_coordinates(
    connection: Connection, experiment_id: int, *, stages_directory: Path
) -> CloudSummary:
    """Fit UMAP over one experiment's feature vectors and persist a 2D coordinate for each sample.

    A full recompute every run, rather than placing only new points into an already-fitted model,
    is a deliberate simplification: UMAP has no natural per-point incremental update without
    persisting and versioning a fitted model, and a full fit is cheap enough at a personal
    library's scale not to need that complexity yet. The fit keeps its finished stages -- the
    neighbor graph, then the coordinates -- under `stages_directory`, named by `layout_digest`, so a
    run stopped partway takes up after the last of them. The experiment is recorded as the one the
    cloud shows in the same transaction that writes the layout, so a recompute either lands
    completely or not at all, and the stages go once it has. Each sample's standardized feature
    vector -- the same one the projection below is fit from -- is persisted alongside its coordinate,
    so a named, reusable "spectral distance" between two samples is always the same metric this
    projection respects.

    ``sample_feature_vector.sample_hash`` foreign-keys to ``sample.hash``, so every vector this
    reads already belongs to a cataloged sample -- promoting an experiment can never reference a
    sample the catalog no longer has.
    """
    feature_vectors = PostgresSampleFeatureVectorRepository(connection).list_for_experiment(experiment_id)
    if len(feature_vectors) < MINIMUM_SAMPLES_FOR_REDUCTION:
        _logger.info(
            "Experiment %d holds %d feature vectors; a layout needs %d, so the cloud stays as it is.",
            experiment_id,
            len(feature_vectors),
            MINIMUM_SAMPLES_FOR_REDUCTION,
        )
        return CloudSummary(samples_reduced=0)

    sample_hashes = [vector.sample_hash for vector in feature_vectors]
    feature_matrix = np.stack([np.array(vector.vector, dtype=np.float64) for vector in feature_vectors])
    standardized = standardize(feature_matrix)
    n_neighbors = neighbor_count(len(sample_hashes))
    membership = PostgresSampleFeatureVectorRepository(connection).membership_digest(experiment_id)
    stages = LayoutStages.open(
        stages_directory, digest=layout_digest(experiment_id, membership=membership, n_neighbors=n_neighbors)
    )
    coordinates = stages.coordinates()
    if coordinates is None:
        _logger.info("Fitting UMAP over %d feature vectors...", len(sample_hashes))
        coordinates = fit_plane(standardized, n_neighbors=n_neighbors, stages=stages)
        stages.keep_coordinates(coordinates)
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
        PostgresCloudPromotionRepository(connection).record(
            CloudPromotion(experiment_id=experiment_id, promoted_at=computed_at)
        )
    stages.discard()
    _logger.info("Persisting complete.")

    return CloudSummary(samples_reduced=len(sample_hashes))
