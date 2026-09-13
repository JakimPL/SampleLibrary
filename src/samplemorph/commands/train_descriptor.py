from __future__ import annotations

import argparse
import logging
from typing import Final

from sqlalchemy import Connection

from samplecore.cli_support import positive_integer
from samplecore.config import LibraryConfig
from samplemorph.commands.run_arguments import add_run_arguments, report_outcome, run_settings_from
from samplemorph.descriptors.grid_descriptor import DEFAULT_WIDTH
from samplemorph.descriptors.learned import DEFAULT_DESCRIPTOR_NAME
from samplemorph.training.descriptor_cache import DEFAULT_GRID_CACHE_NAME, grid_cache_directory, open_grid_cache
from samplemorph.training.descriptor_losses import (
    DEFAULT_DISTILLATION_WEIGHT,
    DEFAULT_LABEL_WEIGHT,
    DEFAULT_RETUNING_WEIGHT,
    DescriptorLossWeights,
)
from samplemorph.training.descriptor_settings import (
    DEFAULT_DESCRIPTOR_BATCH_SIZE,
    DEFAULT_DESCRIPTOR_EPOCHS,
    DEFAULT_DESCRIPTOR_LEARNING_RATE,
    DEFAULT_LABEL_HOLDOUT_SHARE,
    DEFAULT_LABELED_PER_BATCH,
    DescriptorTrainingSettings,
)

COMMAND_NAME: Final[str] = "train-descriptor"
DESCRIPTOR_EXPERIMENT_NAME: Final[str] = "descriptor"

_logger = logging.getLogger(__name__)


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser(
        COMMAND_NAME, help="Teach a descriptor from a grid cache, a teacher experiment and the hand labels."
    )
    parser.add_argument("--cache", type=str, default=DEFAULT_GRID_CACHE_NAME, help="Which grid cache to train over.")
    parser.add_argument(
        "--teacher-experiment",
        type=positive_integer,
        required=True,
        help="The experiment whose vectors the descriptor is distilled from.",
    )
    parser.add_argument(
        "--descriptor", type=str, default=DEFAULT_DESCRIPTOR_NAME, help="The name to store the descriptor under."
    )
    parser.add_argument(
        "--width", type=positive_integer, default=DEFAULT_WIDTH, help="How many channels the first stage has."
    )
    parser.add_argument(
        "--distillation-weight",
        type=float,
        default=DEFAULT_DISTILLATION_WEIGHT,
        help="How much the teacher's vectors say in the loss.",
    )
    parser.add_argument(
        "--retuning-weight",
        type=float,
        default=DEFAULT_RETUNING_WEIGHT,
        help="How much the retuned views say in the loss.",
    )
    parser.add_argument(
        "--label-weight", type=float, default=DEFAULT_LABEL_WEIGHT, help="How much the hand labels say in the loss."
    )
    parser.add_argument(
        "--label-holdout",
        type=float,
        default=DEFAULT_LABEL_HOLDOUT_SHARE,
        help="The share of labeled samples kept from the label term, to be judged on.",
    )
    parser.add_argument(
        "--labeled-per-batch",
        type=positive_integer,
        default=DEFAULT_LABELED_PER_BATCH,
        help="How many taught labeled samples every batch carries.",
    )
    add_run_arguments(parser)
    parser.set_defaults(
        epochs=DEFAULT_DESCRIPTOR_EPOCHS,
        batch=DEFAULT_DESCRIPTOR_BATCH_SIZE,
        learning_rate=DEFAULT_DESCRIPTOR_LEARNING_RATE,
    )


def run(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Train one descriptor and report where its best epoch was written."""
    # The trainer and the run store are imported here, so parsing arguments and the commands that
    # train nothing stay clear of them.
    # pylint: disable=import-outside-toplevel
    from samplecore.tracking.session import open_run
    from samplemorph.training.descriptor_data import load_descriptor_corpus
    from samplemorph.training.descriptor_run import run_descriptor_training
    from samplemorph.training.runs import RunPlacement

    cache = open_grid_cache(grid_cache_directory(config.library_root, name=arguments.cache))
    settings = DescriptorTrainingSettings(
        run=run_settings_from(arguments),
        weights=DescriptorLossWeights(
            distillation=arguments.distillation_weight,
            retuning=arguments.retuning_weight,
            labels=arguments.label_weight,
        ),
        width=arguments.width,
        label_holdout_share=arguments.label_holdout,
        labeled_per_batch=arguments.labeled_per_batch,
    )
    corpus = load_descriptor_corpus(
        connection,
        cache=cache,
        library_root=config.library_root,
        teacher_experiment_id=arguments.teacher_experiment,
        settings=settings,
    )
    _logger.info(
        "Training over %d cached samples, %d labeled by hand of which %d are held out.",
        corpus.sample_count,
        len(corpus.labels),
        len(corpus.held_out_labeled_positions),
    )
    with open_run(
        config.library_root,
        recorded=not arguments.no_tracking,
        experiment_name=DESCRIPTOR_EXPERIMENT_NAME,
        run_name=arguments.descriptor,
    ) as tracker:
        outcome = run_descriptor_training(
            corpus,
            settings=settings,
            placement=RunPlacement(
                library_root=config.library_root,
                model_name=arguments.descriptor,
                tracker=tracker,
                resume=arguments.resume,
            ),
        )

    report_outcome(outcome)
