from __future__ import annotations

import argparse
from typing import Final

from sqlalchemy import Connection

from samplecore.config import LibraryConfig
from samplemorph.commands.analysis_training import (
    AnalysisTrainer,
    AnalysisTrainingFlags,
    add_analysis_training_arguments,
    train_on_analysis_corpus,
)
from samplemorph.vocoders.learned import DEFAULT_PHASE_MODEL_NAME
from samplemorph.vocoders.phase_model import DEFAULT_CHANNELS

COMMAND_NAME: Final[str] = "train-phase"
PHASE_EXPERIMENT_NAME: Final[str] = "phase-vocoder"
DEFAULT_TRAIN_SAMPLE_COUNT: Final[int] = 20_000
FLAGS: Final[AnalysisTrainingFlags] = AnalysisTrainingFlags(
    axis_help="Which frequency axis the magnitudes are produced on.",
    sample_count=DEFAULT_TRAIN_SAMPLE_COUNT,
    channels=DEFAULT_CHANNELS,
    model_flag="--phase-model",
    model_name=DEFAULT_PHASE_MODEL_NAME,
)


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser(COMMAND_NAME, help="Teach a phase model the phase this pipeline's magnitudes carry.")
    add_analysis_training_arguments(parser, FLAGS)


def run(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Teach a phase model on the magnitudes this pipeline's own canonicalizer produces, under the default loss weights."""
    # The trainer is imported here, so parsing arguments and the commands that train nothing stay
    # clear of it.
    # pylint: disable=import-outside-toplevel
    from samplemorph.training.phase_losses import LossWeights
    from samplemorph.training.phase_run import run_phase_training

    trainer = AnalysisTrainer(
        experiment_name=PHASE_EXPERIMENT_NAME,
        model_name=arguments.phase_model,
        train=lambda corpus, settings, placement: run_phase_training(
            corpus, settings=settings, weights=LossWeights(), placement=placement
        ),
    )
    train_on_analysis_corpus(connection, config, arguments, trainer)
