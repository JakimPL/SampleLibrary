from __future__ import annotations

import argparse
import logging
from typing import Final

from sqlalchemy import Connection

from samplecore.cli_parsing import add_subcommand
from samplecore.config import LibraryConfig
from samplemorph.commands.run_arguments import add_cached_training_arguments, run_settings_from, train_and_report
from samplemorph.coordinates.pitch_head.shape import DEFAULT_HEAD_TRUST
from samplemorph.training.frame_cache import DEFAULT_FRAME_CACHE_NAME, frame_cache_directory, open_frame_cache
from samplemorph.training.pitch.settings import (
    DEFAULT_EQUIVARIANCE_WEIGHT,
    DEFAULT_INVARIANCE_WEIGHT,
    DEFAULT_PITCH_BATCH_SIZE,
    DEFAULT_PITCH_EPOCHS,
    DEFAULT_PITCH_LEARNING_RATE,
    DEFAULT_SHIFT_WEIGHT,
    PitchTrainingSettings,
)

COMMAND_NAME: Final[str] = "train-pitch"
PITCH_EXPERIMENT_NAME: Final[str] = "pitch"

_logger = logging.getLogger(__name__)


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = add_subcommand(
        commands,
        COMMAND_NAME,
        summary="Teach a pitch head over a frame cache, on crops of one frame whose distance apart is known.",
    )
    parser.add_argument("--cache", type=str, default=DEFAULT_FRAME_CACHE_NAME, help="Which frame cache to train over.")
    parser.add_argument("--head", type=str, required=True, help="The name to store the pitch head under.")
    parser.add_argument(
        "--equivariance-weight",
        type=float,
        default=DEFAULT_EQUIVARIANCE_WEIGHT,
        help="How much the distance between two crops' answers says in the loss.",
    )
    parser.add_argument(
        "--shift-weight",
        type=float,
        default=DEFAULT_SHIFT_WEIGHT,
        help="How much one crop's answer held against the other's, moved by the shift between them, says in the loss.",
    )
    parser.add_argument(
        "--invariance-weight",
        type=float,
        default=DEFAULT_INVARIANCE_WEIGHT,
        help="How much two augmentations of one crop answering alike says in the loss.",
    )
    parser.add_argument(
        "--trust",
        type=float,
        default=DEFAULT_HEAD_TRUST,
        help="The reliability from which the stored head's readings are trusted, which a gliding route reads.",
    )
    add_cached_training_arguments(
        parser,
        epochs=DEFAULT_PITCH_EPOCHS,
        batch_size=DEFAULT_PITCH_BATCH_SIZE,
        learning_rate=DEFAULT_PITCH_LEARNING_RATE,
    )


def run(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Train one pitch head and report where its best epoch was written."""
    # The trainer and the run store are imported here, so parsing arguments and the commands that
    # train nothing stay clear of them.
    # pylint: disable=import-outside-toplevel
    from samplecore.tracking.session import open_run
    from samplemorph.training.pitch.run import run_pitch_training
    from samplemorph.training.run_paths import RunFamily
    from samplemorph.training.runs import RunPlacement, TrainingOutcome, check_resume_point
    from samplemorph.training.splits import split_corpus

    cache = open_frame_cache(frame_cache_directory(config.library_root, name=arguments.cache))

    def train() -> TrainingOutcome:
        check_resume_point(config.library_root, family=RunFamily.PITCH, name=arguments.head, resume=arguments.resume)
        settings = PitchTrainingSettings(
            run=run_settings_from(arguments),
            equivariance_weight=arguments.equivariance_weight,
            shift_weight=arguments.shift_weight,
            invariance_weight=arguments.invariance_weight,
            validation_share=arguments.validation_share,
            trusted_reliability=arguments.trust,
        )
        corpus = split_corpus(connection, cache=cache, library_root=config.library_root, settings=settings)
        _logger.info(
            "Training over %d cached samples, %d held out by equivalence class, on frames of %d bands.",
            len(corpus.training_positions),
            len(corpus.validation_positions),
            cache.description.analysis.band_count,
        )
        with open_run(
            config.library_root,
            recorded=not arguments.no_tracking,
            experiment_name=PITCH_EXPERIMENT_NAME,
            run_name=arguments.head,
        ) as tracker:
            return run_pitch_training(
                corpus,
                settings=settings,
                placement=RunPlacement(
                    library_root=config.library_root,
                    family=RunFamily.PITCH,
                    model_name=arguments.head,
                    tracker=tracker,
                    resume=arguments.resume,
                ),
            )

    train_and_report(train)
