from __future__ import annotations

import argparse
import logging
from typing import Final

from sqlalchemy import Connection

from samplecloud.backends.teacher_backend import TEACHER_BACKEND_NAME, TEACHER_CHECKPOINT, load_teacher
from samplecloud.suggestions.scoring import (
    DEFAULT_SUGGESTION_COUNT,
    MAXIMUM_SUGGESTION_COUNT,
    ScoringRecipe,
    ScoringSummary,
    score_suggestions,
)
from samplecloud.suggestions.vocabulary import INSTRUMENTS_CHOICE, prompt_for, vocabulary_from
from samplecore.cli_support import bootstrap_cli, integer_between, open_catalog_connection, positive_integer
from samplecore.models.experiment import Experiment
from samplecore.storage.repositories.experiment import PostgresExperimentRepository

DEFAULT_TEXT_DEVICE: Final[str] = "cpu"

_logger = logging.getLogger(__name__)


def main(argv: list[str], *, prog: str) -> None:
    """Suggest labels for every sample of a listening-model experiment, and report how they read."""
    arguments = _parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    with open_catalog_connection(config.database_url) as connection:
        source = _listening_experiment(connection, arguments.experiment_id)
        vocabulary = vocabulary_from(arguments.vocabulary, connection)
        prompts = load_teacher(device=arguments.device).embed_text([prompt_for(label) for label in vocabulary])
        summary = score_suggestions(
            connection,
            recipe=ScoringRecipe(
                source_experiment_id=source.id,
                checkpoint=TEACHER_CHECKPOINT,
                vocabulary=vocabulary,
                suggestion_count=arguments.top,
                label=arguments.label,
            ),
            prompts=prompts,
        )
    _report(summary)


def _listening_experiment(connection: Connection, experiment_id: int) -> Experiment:
    """The experiment whose vectors are scored, which has to come from the listening model the prompts share a space with.

    Raises:
        ValueError: the catalog holds no such experiment, or another backend extracted it.
    """
    experiment = PostgresExperimentRepository(connection).get(experiment_id)
    if experiment is None:
        raise ValueError(f"the catalog holds no experiment {experiment_id}")
    if experiment.backend_name != TEACHER_BACKEND_NAME:
        raise ValueError(
            f"experiment {experiment_id} was extracted by the {experiment.backend_name} backend; "
            f"suggestions read the {TEACHER_BACKEND_NAME} backend's vectors"
        )
    return experiment


def _report(summary: ScoringSummary) -> None:
    _logger.info("Experiment %d: suggested labels for %d samples.", summary.experiment_id, summary.sample_count)
    for label, count in sorted(summary.first_picks.items(), key=lambda item: (-item[1], item[0])):
        _logger.info("  %-24s %6d  %5.1f%%", label, count, 100.0 * count / summary.sample_count)
    agreement = summary.agreement
    if agreement.labeled:
        _logger.info(
            "Against %d hand labels the first suggestion agrees exactly on %d (%.1f%%) and by category on %d (%.1f%%).",
            agreement.labeled,
            agreement.exact,
            100.0 * agreement.exact / agreement.labeled,
            agreement.category,
            100.0 * agreement.category / agreement.labeled,
        )


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=prog, description="Suggest labels for every sample of a listening-model experiment."
    )
    parser.add_argument(
        "--experiment-id",
        type=positive_integer,
        required=True,
        help="The listening-model experiment whose vectors are scored.",
    )
    parser.add_argument(
        "--vocabulary",
        type=str,
        default=INSTRUMENTS_CHOICE,
        help="Which labels to rank: instruments, hand-labels, or a file with one label per line.",
    )
    parser.add_argument(
        "--top",
        type=integer_between(1, MAXIMUM_SUGGESTION_COUNT),
        default=DEFAULT_SUGGESTION_COUNT,
        help="How many labels each sample keeps, closest first.",
    )
    parser.add_argument(
        "--device", type=str, default=DEFAULT_TEXT_DEVICE, help="Which device the text tower reads the prompts on."
    )
    parser.add_argument("--label", type=str, default=None, help="A human-readable note for the scoring's experiment.")
    return parser.parse_args(argv)
