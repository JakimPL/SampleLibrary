from __future__ import annotations

import argparse
from typing import Final

from sqlalchemy import Connection

from samplecore.cli_parsing import add_subcommand
from samplecore.config import LibraryConfig
from samplemorph.commands.analysis_training import (
    AnalysisTrainer,
    AnalysisTrainingFlags,
    add_analysis_training_arguments,
    train_on_analysis_corpus,
)
from samplemorph.model_paths import DEFAULT_RESTORER_NAME
from samplemorph.training.restorer_settings import (
    DEFAULT_RESTORER_BATCH_SIZE,
    DEFAULT_RESTORER_EPOCHS,
    DEFAULT_RESTORER_LEARNING_RATE,
    DEFAULT_RESTORER_PRECISION,
)
from samplemorph.vocoders.restorer_shape import DEFAULT_CHANNELS, GROUP_COUNT

COMMAND_NAME: Final[str] = "train-restorer"
RESTORER_EXPERIMENT_NAME: Final[str] = "restorer"
# The restorer is taught what this library's own sounds carry, so it reads every sample by default.
FLAGS: Final[AnalysisTrainingFlags] = AnalysisTrainingFlags(
    axis_help="Which frequency axis the magnitudes are read back from.",
    sample_count=None,
    channels=DEFAULT_CHANNELS,
    channel_step=GROUP_COUNT,
    model_flag="--restorer",
    model_name=DEFAULT_RESTORER_NAME,
)


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = add_subcommand(
        commands,
        COMMAND_NAME,
        summary="Teach a restorer the fine structure the grid removes from this pipeline's magnitudes.",
    )
    add_analysis_training_arguments(parser, FLAGS)
    parser.set_defaults(
        epochs=DEFAULT_RESTORER_EPOCHS,
        batch=DEFAULT_RESTORER_BATCH_SIZE,
        learning_rate=DEFAULT_RESTORER_LEARNING_RATE,
        precision=DEFAULT_RESTORER_PRECISION,
    )


def run(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Teach a restorer on the magnitudes this pipeline's own canonicalizer reads back."""
    # The trainer is imported here, so parsing arguments and the commands that train nothing stay
    # clear of it.
    # pylint: disable=import-outside-toplevel
    from samplemorph.training.restorer_run import run_restorer_training
    from samplemorph.training.run_paths import RunFamily

    trainer = AnalysisTrainer(
        experiment_name=RESTORER_EXPERIMENT_NAME,
        family=RunFamily.RESTORER,
        model_name=arguments.restorer,
        train=lambda corpus, settings, placement: run_restorer_training(corpus, settings=settings, placement=placement),
    )
    train_on_analysis_corpus(connection, config, arguments, trainer)
