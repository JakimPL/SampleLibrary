from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Connection

from samplecloud.backends import FeatureExtractor
from samplecloud.features import FeatureExtractionSummary, extract_features
from samplecloud.reduce import CloudSummary, reduce_and_persist_coordinates
from samplecore.config import LibraryConfig
from samplecore.models.experiment import Experiment
from samplecore.storage.repositories.experiment import PostgresExperimentRepository


@dataclass(frozen=True)
class EmbeddingSummary:
    """What one embedding run did, across both its extraction and reduction stages."""

    experiment_id: int
    extraction: FeatureExtractionSummary
    reduction: CloudSummary


def resolve_experiment(
    connection: Connection,
    *,
    backend_name: str,
    label: str | None = None,
    params: dict[str, Any] | None = None,
    experiment_id: int | None = None,
) -> int:
    """Return the id of the experiment a caller's extraction run should write into.

    Creates a new ``Experiment`` row, committed immediately so a later resume can find it even if
    extraction itself is interrupted, when ``experiment_id`` is not given. Passing an existing one
    instead resumes that experiment, verified to actually exist first -- two experiments, whether
    different backends or different parameters of the same backend, extract independently, so
    resuming the wrong id would silently mix one experiment's vectors into another's.

    Raises:
        ValueError: ``experiment_id`` is given but no such experiment exists to resume.
    """
    experiment_repository = PostgresExperimentRepository(connection)
    if experiment_id is not None:
        if experiment_repository.get(experiment_id) is None:
            raise ValueError(f"No experiment with id {experiment_id} exists to resume.")
        return experiment_id

    new_experiment_id = experiment_repository.next_id()
    experiment_repository.insert(
        Experiment(
            id=new_experiment_id,
            backend_name=backend_name,
            params=params or {},
            created_at=datetime.now(UTC),
            label=label,
        )
    )
    connection.commit()
    return new_experiment_id


def run_embedding(
    config: LibraryConfig,
    connection: Connection,
    feature_extractor: FeatureExtractor,
    experiment_id: int,
    *,
    sample_limit: int | None = None,
) -> EmbeddingSummary:
    """Extract every missing sample's feature vector for the given experiment, then re-fit its 2D layout.

    ``experiment_id`` must already exist -- see ``resolve_experiment`` for creating a new experiment
    or validating one to resume before calling this.
    """
    extraction = extract_features(
        connection, config.library_root, experiment_id, feature_extractor, sample_limit=sample_limit
    )
    reduction = reduce_and_persist_coordinates(connection, experiment_id)
    return EmbeddingSummary(experiment_id=experiment_id, extraction=extraction, reduction=reduction)
