from __future__ import annotations

import argparse
import logging
from pathlib import Path

from sqlalchemy import Connection

from samplecloud.backends import FeatureExtractor
from samplecloud.evaluation.categories import CategoryAgreement
from samplecloud.evaluation.harness import evaluate_experiment
from samplecloud.evaluation.notes import NoteAgreement
from samplecloud.evaluation.report import EvaluationReport, report_json
from samplecloud.evaluation.settings import (
    DEFAULT_PROBE_COUNT,
    DEFAULT_RANDOM_SEED,
    EvaluationSettings,
)
from samplecloud.evaluation.transposition import TranspositionRetrieval
from samplecloud.registries import BACKEND_REGISTRY
from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from samplecore.storage.repositories.experiment import PostgresExperimentRepository

_logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    """Score one experiment's descriptor and report what it measured."""
    arguments = _parse_arguments(argv)
    config = bootstrap_cli()
    with open_catalog_connection(config.database_url) as connection:
        report = evaluate_experiment(
            connection,
            experiment_id=arguments.experiment_id,
            library_root=config.library_root,
            feature_extractor=_extractor_for(connection, arguments),
            settings=EvaluationSettings(random_seed=arguments.seed, probe_count=arguments.probes),
        )

    if arguments.output is not None:
        output = Path(arguments.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report_json(report), encoding="utf-8")
        _logger.info("Wrote the report to %s.", output)

    _report(report)


def _extractor_for(connection: Connection, arguments: argparse.Namespace) -> FeatureExtractor | None:
    """The extractor that produced this experiment, which retrieval needs to describe audio again.

    Raises:
        ValueError: the catalog holds no such experiment, or names a backend this build lacks.
    """
    if arguments.skip_transposition:
        return None

    experiment = PostgresExperimentRepository(connection).get(arguments.experiment_id)
    if experiment is None:
        raise ValueError(f"the catalog holds no experiment {arguments.experiment_id}")
    if experiment.backend_name not in BACKEND_REGISTRY:
        raise ValueError(
            f"experiment {arguments.experiment_id} was extracted by the unknown {experiment.backend_name} backend"
        )

    return BACKEND_REGISTRY[experiment.backend_name]()


def _report(report: EvaluationReport) -> None:
    """Log what the pass measured, in the order the metrics answer their questions."""
    _logger.info(
        "Experiment %d (%s), %d samples, seed %d.",
        report.experiment_id,
        report.backend_name,
        report.sample_count,
        report.random_seed,
    )
    if report.transposition is not None:
        _report_transposition(report.transposition)
    if report.categories is not None:
        _report_categories(report.categories)
    if report.notes is not None:
        _report_notes(report.notes)


def _report_transposition(retrieval: TranspositionRetrieval) -> None:
    _logger.info(
        "Transposition retrieval over %d probes against %d samples: rank-1 %.1f%%, median rank %.0f.",
        retrieval.probe_sample_count,
        retrieval.catalog_sample_count,
        100.0 * retrieval.rank_one_share,
        retrieval.median_rank,
    )
    for offset in retrieval.offsets:
        _logger.info(
            "  %+5.0f st: rank-1 %5.1f%%, rank-5 %5.1f%%, median rank %8.0f, over %d trials.",
            offset.semitone_offset,
            100.0 * offset.rank_one_share,
            100.0 * offset.close_rank_share,
            offset.median_rank,
            offset.trial_count,
        )


def _report_categories(agreement: CategoryAgreement) -> None:
    _logger.info(
        "Category agreement over %d keyword-labeled samples (%.1f%% of the catalog): accuracy %.3f, macro-F1 %.3f.",
        agreement.scored_sample_count,
        100.0 * agreement.coverage,
        agreement.accuracy,
        agreement.macro_f1,
    )
    for score in sorted(agreement.per_category, key=lambda entry: entry.support, reverse=True):
        _logger.info("  %-14s F1 %.3f over %5d samples.", score.category, score.f1, score.support)


def _report_notes(agreement: NoteAgreement) -> None:
    _logger.info(
        "Note-event agreement over %d samples (%.1f%% of the catalog), %d struck often enough to read from.",
        agreement.scored_sample_count,
        100.0 * agreement.coverage,
        agreement.well_struck_sample_count,
    )
    for score in agreement.targets:
        _logger.info("  %-18s Spearman %+.3f.", score.target, score.spearman)
    for score in agreement.well_struck_targets:
        _logger.info("  %-18s Spearman %+.3f, over the well-struck samples alone.", score.target, score.spearman)
    _logger.info("  single-pitch AUC %.3f, secondary and carrying the same censoring.", agreement.single_pitch_auc)


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score one experiment's descriptor against the catalog's own targets.")
    parser.add_argument("--experiment-id", type=int, required=True, help="Which experiment's vectors to score.")
    parser.add_argument(
        "--probes",
        type=int,
        default=DEFAULT_PROBE_COUNT,
        help="How many samples to retune for transposition retrieval.",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED, help="The seed every split and draw uses.")
    parser.add_argument("--output", type=str, default=None, help="Where to write the report as JSON, if anywhere.")
    parser.add_argument(
        "--skip-transposition",
        action="store_true",
        help="Score the stored vectors alone, leaving out the pass that reads and describes audio again.",
    )
    return parser.parse_args(argv)
