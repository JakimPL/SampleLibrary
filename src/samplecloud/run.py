from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Connection

from samplecloud.backends import FeatureExtractor
from samplecloud.experiments import EmbeddingRecipe, ExperimentRefused, require_reproducible
from samplecloud.features import FeatureExtractionSummary, FeaturePass, extract_features, pending_samples
from samplecloud.hearing import hearing_for
from samplecloud.reduce import CloudSummary, reduce_and_persist_coordinates
from samplecloud.registries import DEFAULT_BACKEND_NAME
from samplecore.config import LibraryConfig
from samplecore.models.cloud import CloudPromotion
from samplecore.models.experiment import ExperimentKey, Reading
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.cloud import PostgresCloudCoordinateRepository, PostgresCloudPromotionRepository
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.sample_audio import SampleAudio

REBUILT_RECIPE = EmbeddingRecipe(backend_name=DEFAULT_BACKEND_NAME, reading=Reading.NOMINAL, model_name=None)

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmbeddingOptions:
    """How one embedding run goes: how it reads a sample, over how many, and whether it becomes the cloud shown.

    An experiment extracted to be measured, or to teach another descriptor, keeps its vectors and
    leaves the cloud as it was.
    """

    reading: Reading
    sample_limit: int | None
    promote: bool


@dataclass(frozen=True)
class EmbeddingSummary:
    """What one embedding run did: its extraction stage, and its reduction stage when it ran one."""

    experiment_id: int
    extraction: FeatureExtractionSummary
    reduction: CloudSummary | None


def create_experiment(
    connection: Connection, recipe: EmbeddingRecipe, *, label: str | None, key: ExperimentKey | None
) -> int:
    """Open a new experiment recording ``recipe``, committed at once so a later resume can find it by its id or key."""
    return PostgresExperimentRepository(connection).create(
        backend_name=recipe.backend_name, label=label, params=recipe.parameters, key=key
    )


def experiment_to_rebuild(connection: Connection) -> int:
    """The experiment a rebuild resumes: the one the cloud shows, or a new librosa one for a library with no cloud yet.

    A new experiment is recorded as the one on show in the same commit that opens it, so a first
    rebuild interrupted during extraction resumes that experiment the next time rather than opening
    another.

    Raises:
        ExperimentRefused: the catalog holds cloud coordinates but no record of the experiment they came from.
    """
    promotion = PostgresCloudPromotionRepository(connection).current()
    if promotion is not None:
        return promotion.experiment_id
    if PostgresCloudCoordinateRepository(connection).revision()[0] > 0:
        raise ExperimentRefused(
            "the cloud shows coordinates with no record of the experiment they came from; "
            "`samplelibrary cloud embed --experiment-id N` lays out experiment N and records it"
        )

    with start_batch(connection):
        experiment_id = PostgresExperimentRepository(connection).insert_new(
            backend_name=REBUILT_RECIPE.backend_name, label=None, params=REBUILT_RECIPE.parameters, key=None
        )
        PostgresCloudPromotionRepository(connection).record(
            CloudPromotion(experiment_id=experiment_id, promoted_at=datetime.now(UTC))
        )
    return experiment_id


def run_embedding(
    config: LibraryConfig,
    connection: Connection,
    experiment_id: int,
    *,
    extractor: Callable[[], FeatureExtractor],
    options: EmbeddingOptions,
) -> EmbeddingSummary:
    """Extract every missing sample's feature vector for the given experiment, then lay the cloud out from it.

    The extractor is built only once a sample is found missing, so a pass with nothing new to
    describe loads no model. Before new vectors join an experiment that already holds some, a few of
    its samples are described again and must match (see ``require_reproducible``). A promoting run
    that adds nothing to the experiment the cloud already shows keeps the cloud's layout as it is.

    Raises:
        ExtractorChanged: the extractor no longer reproduces the experiment's own vectors.
        ExperimentRefused: none of the experiment's samples can be read now to check the extractor against.
    """
    pending = pending_samples(connection, experiment_id, sample_limit=options.sample_limit)
    if pending.samples:
        feature_extractor = extractor()
        hearing = hearing_for(connection, options.reading)
        audio = SampleAudio.from_catalog(connection, config.library_root)
        if pending.already_extracted:
            require_reproducible(
                connection,
                audio,
                experiment_id=experiment_id,
                extractor=feature_extractor,
                hearing=hearing,
            )
        extraction = extract_features(
            connection,
            audio,
            FeaturePass(experiment_id=experiment_id, feature_extractor=feature_extractor, hearing=hearing),
            pending,
        )
    else:
        extraction = FeatureExtractionSummary(
            cataloged=pending.cataloged, already_extracted=pending.already_extracted, newly_extracted=0, unavailable=0
        )

    return EmbeddingSummary(
        experiment_id=experiment_id,
        extraction=extraction,
        reduction=_laid_out(connection, experiment_id, extraction=extraction) if options.promote else None,
    )


def _laid_out(
    connection: Connection, experiment_id: int, *, extraction: FeatureExtractionSummary
) -> CloudSummary | None:
    promotion = PostgresCloudPromotionRepository(connection).current()
    shown = promotion is not None and promotion.experiment_id == experiment_id
    if shown and extraction.newly_extracted == 0 and PostgresCloudCoordinateRepository(connection).revision()[0] > 0:
        _logger.info(
            "The cloud already shows experiment %d with every sample it holds, so its layout stays.", experiment_id
        )
        return None
    return reduce_and_persist_coordinates(connection, experiment_id)
