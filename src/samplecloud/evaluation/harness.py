from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Connection

from samplecloud.backends import FeatureExtractor
from samplecloud.evaluation.categories import category_agreement
from samplecloud.evaluation.corpus import EvaluationCorpus, load_corpus
from samplecloud.evaluation.notes import note_agreement
from samplecloud.evaluation.report import EvaluationReport
from samplecloud.evaluation.settings import EvaluationSettings
from samplecloud.evaluation.transposition import TranspositionRetrieval, transposition_retrieval
from samplecore.storage.repositories.experiment import PostgresExperimentRepository

_logger = logging.getLogger(__name__)


def evaluate_experiment(
    connection: Connection,
    *,
    experiment_id: int,
    library_root: Path,
    feature_extractor: FeatureExtractor | None,
    settings: EvaluationSettings,
) -> EvaluationReport:
    """Score one experiment's descriptor against every target the catalog can supply.

    Each metric runs against the same corpus and the same settings, so two runs of this function
    reproduce every number. Passing a `feature_extractor` adds transposition retrieval, which reads
    audio and describes it again; the other two metrics read the stored vectors alone.

    Raises:
        ValueError: the catalog holds no experiment under that identifier.
    """
    experiment = PostgresExperimentRepository(connection).get(experiment_id)
    if experiment is None:
        raise ValueError(f"the catalog holds no experiment {experiment_id}")

    _logger.info("Loading experiment %d and its evaluation targets...", experiment_id)
    corpus = load_corpus(connection, experiment_id=experiment_id)
    _logger.info(
        "Scoring %d vectors: %d keyword-labeled, %d reached by note events.",
        corpus.sample_count,
        int(corpus.categorized.sum()),
        int(corpus.note_reached.sum()),
    )
    return EvaluationReport(
        experiment_id=experiment_id,
        backend_name=experiment.backend_name,
        sample_count=corpus.sample_count,
        random_seed=settings.random_seed,
        evaluated_at=datetime.now(UTC),
        transposition=_transposition(
            connection,
            corpus,
            library_root=library_root,
            feature_extractor=feature_extractor,
            settings=settings,
        ),
        categories=category_agreement(corpus, settings=settings),
        notes=note_agreement(corpus, settings=settings),
    )


def _transposition(
    connection: Connection,
    corpus: EvaluationCorpus,
    *,
    library_root: Path,
    feature_extractor: FeatureExtractor | None,
    settings: EvaluationSettings,
) -> TranspositionRetrieval | None:
    if feature_extractor is None:
        _logger.info("No extractor given, so transposition retrieval is left out of this pass.")
        return None

    _logger.info("Retuning %d probes across the offset grid...", settings.probe_count)
    return transposition_retrieval(
        connection,
        corpus,
        library_root=library_root,
        feature_extractor=feature_extractor,
        settings=settings,
    )
