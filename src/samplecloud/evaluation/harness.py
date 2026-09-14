from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import Connection

from samplecloud.evaluation.categories import category_agreement
from samplecloud.evaluation.corpus import EvaluationCorpus, load_corpus
from samplecloud.evaluation.hand_labels import MINIMUM_LABELED_SAMPLES, HandLabelAgreement, hand_label_agreement
from samplecloud.evaluation.notes import note_agreement
from samplecloud.evaluation.report import EvaluationReport
from samplecloud.evaluation.settings import EvaluationSettings
from samplecloud.evaluation.transposition import ProbeDescriber, TranspositionRetrieval, transposition_retrieval
from samplecloud.experiments import experiment_named

_logger = logging.getLogger(__name__)


def evaluate_experiment(
    connection: Connection,
    *,
    experiment_id: int,
    describer: ProbeDescriber | None,
    settings: EvaluationSettings,
) -> EvaluationReport:
    """Score one experiment's descriptor against every target the catalog can supply.

    Each metric runs against the same corpus and the same settings, so two runs of this function
    reproduce every number. The metrics reading stored vectors alone come first; passing a
    `describer` then adds transposition retrieval, which reads audio and describes it again. A
    metric the corpus cannot support is left out of the report with a log line naming why.

    Raises:
        ExperimentRefused: the catalog holds no experiment under that identifier.
    """
    experiment = experiment_named(connection, experiment_id)
    _logger.info("Loading experiment %d and its evaluation targets...", experiment_id)
    corpus = load_corpus(connection, experiment_id=experiment_id)
    _logger.info(
        "Scoring %d vectors: %d keyword-labeled, %d reached by note events, %d labeled by hand.",
        corpus.sample_count,
        int(corpus.categorized.sum()),
        int(corpus.note_reached.sum()),
        int(corpus.labeled.sum()),
    )
    categories = category_agreement(corpus, settings=settings)
    if categories is None:
        _logger.info("Too few keyword categories or equivalence groups to fold, so category agreement is left out.")
    notes = note_agreement(corpus, settings=settings)
    if notes is None:
        _logger.info("The note events reach too few equivalence groups to fold, so note agreement is left out.")
    hand_labels = _hand_labels(corpus, settings=settings)
    return EvaluationReport(
        experiment_id=experiment_id,
        backend_name=experiment.backend_name,
        sample_count=corpus.sample_count,
        random_seed=settings.random_seed,
        evaluated_at=datetime.now(UTC),
        transposition=_transposition(connection, corpus, describer=describer, settings=settings),
        categories=categories,
        notes=notes,
        hand_labels=hand_labels,
    )


def _hand_labels(corpus: EvaluationCorpus, *, settings: EvaluationSettings) -> HandLabelAgreement | None:
    labeled_count = int(corpus.labeled.sum())
    if labeled_count < MINIMUM_LABELED_SAMPLES:
        _logger.info(
            "%d samples are labeled by hand, and %d are needed before a hand-label score is read.",
            labeled_count,
            MINIMUM_LABELED_SAMPLES,
        )
        return None

    return hand_label_agreement(corpus, settings=settings)


def _transposition(
    connection: Connection,
    corpus: EvaluationCorpus,
    *,
    describer: ProbeDescriber | None,
    settings: EvaluationSettings,
) -> TranspositionRetrieval | None:
    if describer is None:
        _logger.info("No extractor given, so transposition retrieval is left out of this pass.")
        return None

    _logger.info("Retuning %d probes across the offset grid...", settings.probe_count)
    retrieval = transposition_retrieval(connection, corpus, describer=describer, settings=settings)
    if retrieval is None:
        _logger.info("No probe sample is left in the catalog, so transposition retrieval is left out.")
    return retrieval
