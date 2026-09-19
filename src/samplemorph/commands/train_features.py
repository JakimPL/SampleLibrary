from __future__ import annotations

import argparse
import logging
from typing import Final

from sqlalchemy import Connection

from samplecore.cli_parsing import add_subcommand
from samplecore.cli_support import positive_integer
from samplecore.config import LibraryConfig
from samplemorph.commands.run_arguments import add_run_arguments, run_settings_from, train_and_report
from samplemorph.features.shape import DEFAULT_FEATURE_WIDTH, DEFAULT_LATENT_SIZE
from samplemorph.training.descriptor_cache import DEFAULT_GRID_CACHE_NAME, grid_cache_directory, open_grid_cache
from samplemorph.training.features.settings import (
    DEFAULT_CRITIC_MIX,
    DEFAULT_FEATURE_BATCH_SIZE,
    DEFAULT_FEATURE_EPOCHS,
    DEFAULT_FEATURE_LEARNING_RATE,
    FeatureTrainingSettings,
)
from samplemorph.training.splits import DEFAULT_VALIDATION_SHARE

COMMAND_NAME: Final[str] = "train-features"
FEATURES_EXPERIMENT_NAME: Final[str] = "features"

_logger = logging.getLogger(__name__)


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = add_subcommand(
        commands,
        COMMAND_NAME,
        summary="Teach a grid autoencoder over a grid cache, against a critic of its own latent interpolants.",
    )
    parser.add_argument("--cache", type=str, default=DEFAULT_GRID_CACHE_NAME, help="Which grid cache to train over.")
    parser.add_argument("--features", type=str, required=True, help="The name to store the feature model under.")
    parser.add_argument(
        "--critic-weight",
        type=float,
        required=True,
        help="How much the critic's reading of the latent interpolants says in the autoencoder's loss; 0 trains it alone.",
    )
    parser.add_argument(
        "--critic-mix",
        type=float,
        default=DEFAULT_CRITIC_MIX,
        help="The share of a sound mixed into its reconstruction for the critic to read as a sound.",
    )
    parser.add_argument(
        "--latent-size", type=positive_integer, default=DEFAULT_LATENT_SIZE, help="How many numbers a latent holds."
    )
    parser.add_argument(
        "--width", type=positive_integer, default=DEFAULT_FEATURE_WIDTH, help="How many channels the first stage has."
    )
    parser.add_argument(
        "--validation-share",
        type=float,
        default=DEFAULT_VALIDATION_SHARE,
        help="The share of cached samples held out by equivalence class, to be judged and read on.",
    )
    add_run_arguments(parser)
    parser.set_defaults(
        epochs=DEFAULT_FEATURE_EPOCHS, batch=DEFAULT_FEATURE_BATCH_SIZE, learning_rate=DEFAULT_FEATURE_LEARNING_RATE
    )


def run(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Train one feature model and report where its best epoch was written."""
    # The trainer and the run store are imported here, so parsing arguments and the commands that
    # train nothing stay clear of them.
    # pylint: disable=import-outside-toplevel
    from samplecore.tracking.session import open_run
    from samplemorph.training.features.data import load_feature_corpus
    from samplemorph.training.features.run import run_feature_training
    from samplemorph.training.run_paths import RunFamily
    from samplemorph.training.runs import RunPlacement, TrainingOutcome, check_resume_point

    cache = open_grid_cache(grid_cache_directory(config.library_root, name=arguments.cache))

    def train() -> TrainingOutcome:
        check_resume_point(
            config.library_root, family=RunFamily.FEATURES, name=arguments.features, resume=arguments.resume
        )
        settings = FeatureTrainingSettings(
            critic_weight=arguments.critic_weight,
            run=run_settings_from(arguments),
            latent_size=arguments.latent_size,
            width=arguments.width,
            critic_mix=arguments.critic_mix,
            validation_share=arguments.validation_share,
        )
        corpus = load_feature_corpus(connection, cache=cache, library_root=config.library_root, settings=settings)
        _logger.info(
            "Training over %d cached samples, %d held out by equivalence class, under critic weight %g.",
            len(corpus.training_positions),
            len(corpus.validation_positions),
            settings.critic_weight,
        )
        with open_run(
            config.library_root,
            recorded=not arguments.no_tracking,
            experiment_name=FEATURES_EXPERIMENT_NAME,
            run_name=arguments.features,
        ) as tracker:
            return run_feature_training(
                corpus,
                settings=settings,
                placement=RunPlacement(
                    library_root=config.library_root,
                    family=RunFamily.FEATURES,
                    model_name=arguments.features,
                    tracker=tracker,
                    resume=arguments.resume,
                ),
            )

    train_and_report(train)
