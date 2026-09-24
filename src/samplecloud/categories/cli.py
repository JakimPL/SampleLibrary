from __future__ import annotations

import argparse
import logging
from typing import Final

from sqlalchemy import Connection

from samplecloud.backends.teacher_backend import (
    TEACHER_BACKEND_NAME,
    TEACHER_CHECKPOINT,
    TEACHER_REVISION,
    load_teacher,
)
from samplecloud.categories.scoring import (
    DEFAULT_CATEGORY_COUNT,
    MAXIMUM_CATEGORY_COUNT,
    ScoringConflict,
    ScoringRecipe,
    ScoringSummary,
    filed_scoring,
    score_categories,
    show_scoring,
)
from samplecloud.categories.vocabulary import INSTRUMENTS_CHOICE, VocabularyRefused, prompt_for, vocabulary_from
from samplecloud.experiments import ExperimentRefused, experiment_named
from samplecore.cli_parsing import command_parser
from samplecore.cli_support import (
    bootstrap_cli,
    ending_in_one_line,
    experiment_key,
    integer_between,
    open_catalog_connection,
    positive_integer,
)
from samplecore.models.experiment import Experiment
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository

DEFAULT_TEXT_DEVICE: Final[str] = "cpu"

_logger = logging.getLogger(__name__)


def main(argv: list[str], *, prog: str) -> None:
    """Give every sample of a listening-model experiment its categories, and report how they read.

    A key files the scoring under a name of its own, so a run naming a key an earlier run filed shows
    that scoring again and scores nothing.
    """
    arguments = parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    with open_catalog_connection(config.catalog_url()) as connection:
        with ending_in_one_line("Scored nothing", (ExperimentRefused, VocabularyRefused, ScoringConflict)):
            source = _listening_experiment(connection, arguments.experiment_id)
            recipe = ScoringRecipe(
                source_experiment_id=source.id,
                checkpoint=TEACHER_CHECKPOINT,
                checkpoint_revision=TEACHER_REVISION,
                vocabulary=vocabulary_from(arguments.vocabulary, connection),
                category_count=arguments.top,
                label=arguments.label,
                key=arguments.key,
            )
            filed = filed_scoring(connection, recipe)
        if filed is not None:
            show_scoring(connection, filed.id)
            _logger.info(
                "Experiment %d already holds the scoring filed under %s, now the one shown.", filed.id, filed.key
            )
            return
        prompts = load_teacher(device=arguments.device).embed_text([prompt_for(label) for label in recipe.vocabulary])
        summary = score_categories(connection, recipe=recipe, prompts=prompts)
    _report(summary)


def _listening_experiment(connection: Connection, experiment_id: int) -> Experiment:
    """The experiment whose vectors are scored, which has to come from the listening model the prompts share a space with.

    Raises:
        ExperimentRefused: the catalog holds no such experiment, another backend extracted it, or it holds no vectors.
    """
    experiment = experiment_named(connection, experiment_id)
    if experiment.backend_name != TEACHER_BACKEND_NAME:
        raise ExperimentRefused(
            f"experiment {experiment_id} was extracted by the {experiment.backend_name} backend; "
            f"a scoring reads the {TEACHER_BACKEND_NAME} backend's vectors"
        )
    if not PostgresSampleFeatureVectorRepository(connection).vectors_in_hash_order(experiment_id, count=1, offset=0):
        raise ExperimentRefused(f"experiment {experiment_id} holds no vectors to score")
    return experiment


def _report(summary: ScoringSummary) -> None:
    _logger.info("Experiment %d: categorized %d samples.", summary.experiment_id, summary.sample_count)
    for label, count in sorted(summary.top_category_counts.items(), key=lambda item: (-item[1], item[0])):
        _logger.info("  %-24s %6d  %5.1f%%", label, count, 100.0 * count / summary.sample_count)
    agreement = summary.agreement
    if agreement.labeled:
        _logger.info(
            "Against %d hand labels the top category agrees exactly on %d (%.1f%%) "
            "and at the top level on %d (%.1f%%).",
            agreement.labeled,
            agreement.exact,
            100.0 * agreement.exact / agreement.labeled,
            agreement.top_level,
            100.0 * agreement.top_level / agreement.labeled,
        )


def parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(prog=prog, description="Give every sample of a listening-model experiment its categories.")
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
        type=integer_between(1, MAXIMUM_CATEGORY_COUNT),
        default=DEFAULT_CATEGORY_COUNT,
        help="How many labels each sample keeps, closest first.",
    )
    parser.add_argument(
        "--device", type=str, default=DEFAULT_TEXT_DEVICE, help="Which device the text tower reads the prompts on."
    )
    parser.add_argument("--label", type=str, default=None, help="A human-readable note for the scoring's experiment.")
    parser.add_argument(
        "--key",
        type=experiment_key,
        default=None,
        help="File the scoring under this key, or show the scoring an earlier run filed under it.",
    )
    return parser.parse_args(argv)
