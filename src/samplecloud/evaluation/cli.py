from __future__ import annotations

import argparse
import logging
from pathlib import Path

from sqlalchemy import Connection

from samplecloud.backends.learned_backend import DEFAULT_LEARNED_DEVICE
from samplecloud.evaluation.hand_labels import HandLabelAgreement
from samplecloud.evaluation.harness import evaluate_experiment
from samplecloud.evaluation.notes import NoteAgreement
from samplecloud.evaluation.recording import EVALUATION_EXPERIMENT_NAME, record_report, run_name_for
from samplecloud.evaluation.report import EvaluationReport, report_json
from samplecloud.evaluation.settings import (
    DEFAULT_EVALUATION_SCOPE,
    DEFAULT_LABEL_DEPTH,
    DEFAULT_PROBE_COUNT,
    DEFAULT_RANDOM_SEED,
    EvaluationScope,
    EvaluationSettings,
)
from samplecloud.evaluation.transposition import ProbeDescriber, TranspositionRetrieval
from samplecloud.experiments import ExperimentRefused, experiment_named, extractor_for, recipe_of
from samplecloud.hearing import hearing_for
from samplecore.cli_parsing import command_parser
from samplecore.cli_support import bootstrap_cli, ending_in_one_line, open_catalog_connection, positive_integer
from samplecore.config import LibraryConfig
from samplecore.models.experiment import Experiment
from samplecore.storage.atomic import write_bytes_atomically
from samplecore.storage.sample_audio import SampleAudio
from samplecore.tracking.session import open_run

_logger = logging.getLogger(__name__)


def main(argv: list[str], *, prog: str) -> None:
    """Score one experiment's descriptor, record the pass, and report what it measured."""
    arguments = parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    with open_catalog_connection(config.catalog_url()) as connection:
        with ending_in_one_line("Scored nothing", (ExperimentRefused,)):
            experiment = experiment_named(connection, arguments.experiment_id)
            describer = _describer(connection, experiment, config=config, arguments=arguments)

        with open_run(
            config.library_root,
            recorded=not arguments.no_tracking,
            experiment_name=EVALUATION_EXPERIMENT_NAME,
            run_name=run_name_for(
                backend_name=experiment.backend_name, experiment_id=experiment.id, scope=arguments.scope
            ),
        ) as tracker:
            report = evaluate_experiment(
                connection,
                experiment_id=experiment.id,
                describer=describer,
                settings=EvaluationSettings(
                    random_seed=arguments.seed,
                    probe_count=arguments.probes,
                    label_depth=arguments.label_depth,
                    scope=arguments.scope,
                ),
            )
            record_report(report, tracker)

    if arguments.output is not None:
        output = Path(arguments.output)
        write_bytes_atomically(output, report_json(report).encode("utf-8"))
        _logger.info("Wrote the report to %s.", output)

    _report(report)


def _describer(
    connection: Connection, experiment: Experiment, *, config: LibraryConfig, arguments: argparse.Namespace
) -> ProbeDescriber | None:
    """The extractor and reading that produced this experiment, which retrieval needs to describe audio again.

    Raises:
        ExperimentRefused: the experiment records no recipe this build can follow.
    """
    if arguments.skip_transposition:
        return None

    recipe = recipe_of(experiment)
    return ProbeDescriber(
        feature_extractor=extractor_for(recipe, library_root=config.library_root, device=arguments.device),
        hearing=hearing_for(connection, recipe.reading),
        audio=SampleAudio.from_catalog(connection, config.library_root),
    )


def _report(report: EvaluationReport) -> None:
    """Log what the pass measured, in the order the metrics answer their questions."""
    _logger.info(
        "Experiment %d (%s), %d samples in the %s scope, seed %d.",
        report.experiment_id,
        report.backend_name,
        report.sample_count,
        report.scope.value,
        report.random_seed,
    )
    if report.transposition is not None:
        _report_transposition(report.transposition)
    if report.notes is not None:
        _report_notes(report.notes)
    if report.hand_labels is not None:
        _report_hand_labels(report.hand_labels)


def _report_transposition(retrieval: TranspositionRetrieval) -> None:
    _logger.info(
        "Transposition retrieval over %d probes (%d with no file to read now) against %d samples: "
        "rank-1 %.1f%%, median rank %.0f.",
        retrieval.probe_sample_count,
        retrieval.unavailable_probe_count,
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


def _report_hand_labels(agreement: HandLabelAgreement) -> None:
    low, high = agreement.ndcg_interval
    _logger.info(
        "Hand-label agreement over %d labeled samples (%.1f%% of the catalog): NDCG %.3f [%.3f, %.3f] "
        "against %.3f by chance, mAP %.3f over %d tags, precision at one %.3f against %.3f by chance.",
        agreement.labeled_sample_count,
        100.0 * agreement.coverage,
        agreement.ndcg,
        low,
        high,
        agreement.ndcg_chance,
        agreement.mean_average_precision,
        len(agreement.per_tag),
        agreement.precision_at_one,
        agreement.precision_at_one_chance,
    )
    for score in agreement.per_tag:
        _logger.info("  %-28s AP %.3f over %4d samples.", score.path, score.average_precision, score.support)


def parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(
        prog=prog, description="Score an experiment's descriptor against the catalog's own targets."
    )
    parser.add_argument(
        "--experiment-id", type=positive_integer, required=True, help="Which experiment's vectors to score."
    )
    parser.add_argument(
        "--probes",
        type=positive_integer,
        default=DEFAULT_PROBE_COUNT,
        help="How many samples to retune for transposition retrieval.",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED, help="The seed every split and draw uses.")
    parser.add_argument(
        "--scope",
        type=EvaluationScope,
        choices=tuple(EvaluationScope),
        default=DEFAULT_EVALUATION_SCOPE,
        help="Which samples to score: every one the experiment describes, or the ones tracker modules hold.",
    )
    parser.add_argument("--output", type=str, default=None, help="Where to write the report as JSON, if anywhere.")
    parser.add_argument(
        "--skip-transposition",
        action="store_true",
        help="Score the stored vectors alone, leaving out the pass that reads and describes audio again.",
    )
    parser.add_argument(
        "--label-depth",
        type=positive_integer,
        default=DEFAULT_LABEL_DEPTH,
        help="How many levels of each hand label to read; every level when left out.",
    )
    parser.add_argument(
        "--no-tracking",
        action="store_true",
        help="Leave this pass out of the run store, for a quick look that is not worth keeping.",
    )
    parser.add_argument(
        "--device", type=str, default=DEFAULT_LEARNED_DEVICE, help="Which device a learned descriptor runs on."
    )
    return parser.parse_args(argv)
