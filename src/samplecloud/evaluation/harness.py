from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import TypeAdapter
from sqlalchemy import Connection

from samplecloud.evaluation.corpus import EvaluationCorpus, load_corpus
from samplecloud.evaluation.hand_labels import MINIMUM_LABELED_SAMPLES, HandLabelAgreement, hand_label_agreement
from samplecloud.evaluation.notes import NoteAgreement, note_agreement
from samplecloud.evaluation.report import EvaluationReport
from samplecloud.evaluation.settings import EvaluationSettings
from samplecloud.evaluation.stages import STAGE_JSON, EvaluationStages
from samplecloud.evaluation.transposition import ProbeDescriber, TranspositionRetrieval, transposition_retrieval
from samplecloud.experiments import experiment_named
from samplecore.digests import digest_of_rows

NOTES_STAGE: Final[str] = "notes"
HAND_LABELS_STAGE: Final[str] = "hand-labels"
NOTES_ADAPTER: Final[TypeAdapter[NoteAgreement | None]] = TypeAdapter(NoteAgreement | None, config=STAGE_JSON)
HAND_LABELS_ADAPTER: Final[TypeAdapter[HandLabelAgreement | None]] = TypeAdapter(
    HandLabelAgreement | None, config=STAGE_JSON
)

_logger = logging.getLogger(__name__)


def evaluate_experiment(
    connection: Connection,
    *,
    experiment_id: int,
    describer: ProbeDescriber | None,
    settings: EvaluationSettings,
    report_path: Path,
) -> EvaluationReport:
    """Score one experiment's descriptor against every target the catalog can supply.

    Each metric runs against the same corpus and the same settings, so two runs of this function
    reproduce every number. The metrics reading stored vectors alone come first; passing a
    `describer` then adds transposition retrieval, which reads audio and describes it again. A
    metric the corpus cannot support is left out of the report with a log line naming why. Every
    finished metric, and every probe described, is kept in the partial beside `report_path`, so a
    pass stopped partway takes up after them; the caller writing the report clears them.

    Raises:
        ExperimentRefused: the catalog holds no experiment under that identifier.
    """
    experiment = experiment_named(connection, experiment_id)
    _logger.info("Loading experiment %d and its evaluation targets...", experiment_id)
    corpus = load_corpus(connection, experiment_id=experiment_id, scope=settings.scope)
    _logger.info(
        "Scoring %d vectors: %d reached by note events, %d labeled by hand.",
        corpus.sample_count,
        int(corpus.note_reached.sum()),
        int(corpus.labeled.sum()),
    )
    stages = EvaluationStages.open(report_path, identity=_identity(experiment_id, corpus, settings=settings))
    notes = stages.kept(NOTES_STAGE, NOTES_ADAPTER, lambda: note_agreement(corpus, settings=settings))
    if notes is None:
        _logger.info("The note events reach too few equivalence groups to fold, so note agreement is left out.")
    hand_labels = stages.kept(HAND_LABELS_STAGE, HAND_LABELS_ADAPTER, lambda: _hand_labels(corpus, settings=settings))
    return EvaluationReport(
        experiment_id=experiment_id,
        backend_name=experiment.backend_name,
        scope=corpus.scope,
        corpus_digest=corpus.membership_digest,
        sample_count=corpus.sample_count,
        random_seed=settings.random_seed,
        evaluated_at=datetime.now(UTC),
        transposition=_transposition(connection, corpus, describer=describer, settings=settings, stages=stages),
        notes=notes,
        hand_labels=hand_labels,
    )


def _identity(experiment_id: int, corpus: EvaluationCorpus, *, settings: EvaluationSettings) -> str:
    """The name of what one pass scores: the experiment, the corpus it reads, and every setting its draws follow."""
    return digest_of_rows(
        [
            (experiment_id, corpus.membership_digest, settings.scope.value, settings.random_seed),
            (settings.probe_count, settings.neighbor_count, settings.fold_count, settings.label_depth),
            settings.semitone_offsets,
        ]
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
    stages: EvaluationStages,
) -> TranspositionRetrieval | None:
    if describer is None:
        _logger.info("No extractor given, so transposition retrieval is left out of this pass.")
        return None

    _logger.info("Retuning %d probes across the offset grid...", settings.probe_count)
    retrieval = transposition_retrieval(connection, corpus, describer=describer, settings=settings, stages=stages)
    if retrieval is None:
        _logger.info("No probe sample is left in the catalog, so transposition retrieval is left out.")
    return retrieval
