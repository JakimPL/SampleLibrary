from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import Connection

from samplecloud.backends import FeatureExtractor
from samplecloud.features import FeatureExtractionSummary, FeaturePass, extract_features
from samplecloud.hearing import Reading, hearing_for
from samplecloud.reduce import CloudSummary, reduce_and_persist_coordinates
from samplecore.config import LibraryConfig
from samplecore.storage.repositories.experiment import PostgresExperimentRepository

READING_PARAMETER: Final[str] = "reading"


@dataclass(frozen=True)
class EmbeddingOptions:
    """How one embedding run goes: how it reads a sample, over how many, and whether it becomes the cloud shown.

    An experiment extracted to be measured, or to teach another descriptor, keeps its vectors and
    leaves the cloud as it was.
    """

    reading: Reading
    sample_limit: int | None
    promote: bool


def reading_parameters(reading: Reading) -> dict[str, Any]:
    """The reading an experiment was extracted under, in the form its row records it."""
    return {READING_PARAMETER: reading.value}


@dataclass(frozen=True)
class EmbeddingSummary:
    """What one embedding run did: its extraction stage, and its reduction stage when it ran one."""

    experiment_id: int
    extraction: FeatureExtractionSummary
    reduction: CloudSummary | None


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

    return experiment_repository.create(backend_name=backend_name, label=label, params=params or {})


def run_embedding(
    config: LibraryConfig,
    connection: Connection,
    feature_extractor: FeatureExtractor,
    experiment_id: int,
    *,
    options: EmbeddingOptions,
) -> EmbeddingSummary:
    """Extract every missing sample's feature vector for the given experiment, then re-fit its 2D layout.

    ``experiment_id`` must already exist -- see ``resolve_experiment`` for creating a new experiment
    or validating one to resume before calling this.
    """
    extraction = extract_features(
        connection,
        config.library_root,
        FeaturePass(
            experiment_id=experiment_id,
            feature_extractor=feature_extractor,
            hearing=hearing_for(connection, options.reading),
            sample_limit=options.sample_limit,
        ),
    )
    reduction = reduce_and_persist_coordinates(connection, experiment_id) if options.promote else None
    return EmbeddingSummary(experiment_id=experiment_id, extraction=extraction, reduction=reduction)
