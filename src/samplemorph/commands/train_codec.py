from __future__ import annotations

import argparse
import logging
from typing import Final

import torch
from sqlalchemy import Connection

from samplecore.config import LibraryConfig
from samplemorph.codecs.conditioned import DEFAULT_CODEC_NAME
from samplemorph.codecs.conditioned_model import DEFAULT_CODEC_WIDTH, DEFAULT_RESIDUAL_SIZE
from samplemorph.commands.run_arguments import add_run_arguments, report_outcome, run_settings_from
from samplemorph.descriptors.learned import DEFAULT_DESCRIPTOR_NAME, descriptor_path, load_descriptor
from samplemorph.training.codec_losses import (
    DEFAULT_CYCLE_WEIGHT,
    DEFAULT_PRIOR_WEIGHT,
    DEFAULT_RECONSTRUCTION_WEIGHT,
    CodecLossWeights,
)
from samplemorph.training.codec_settings import (
    DEFAULT_CODEC_BATCH_SIZE,
    DEFAULT_CODEC_EPOCHS,
    DEFAULT_CODEC_LEARNING_RATE,
    DEFAULT_PRIOR_WARMUP_STEPS,
    CodecTrainingSettings,
)
from samplemorph.training.descriptor_cache import grid_cache_directory, open_grid_cache

COMMAND_NAME: Final[str] = "train-codec"
CODEC_EXPERIMENT_NAME: Final[str] = "conditioned-codec"
DEFAULT_CODEC_CACHE_NAME: Final[str] = "codec"

_logger = logging.getLogger(__name__)


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser(
        COMMAND_NAME, help="Teach a codec that decodes a grid from a stored descriptor's vector and a residual."
    )
    parser.add_argument(
        "--cache", type=str, default=DEFAULT_CODEC_CACHE_NAME, help="Which full-resolution grid cache to train over."
    )
    parser.add_argument(
        "--descriptor", type=str, default=DEFAULT_DESCRIPTOR_NAME, help="Which stored descriptor conditions the codec."
    )
    parser.add_argument("--codec", type=str, default=DEFAULT_CODEC_NAME, help="The name to store the codec under.")
    parser.add_argument(
        "--residual-size", type=int, default=DEFAULT_RESIDUAL_SIZE, help="How many numbers the residual holds."
    )
    parser.add_argument("--width", type=int, default=DEFAULT_CODEC_WIDTH, help="How many channels the first stage has.")
    parser.add_argument(
        "--reconstruction-weight",
        type=float,
        default=DEFAULT_RECONSTRUCTION_WEIGHT,
        help="How much rebuilding the grid says in the loss.",
    )
    parser.add_argument(
        "--prior-weight",
        type=float,
        default=DEFAULT_PRIOR_WEIGHT,
        help="How much the residual's prior says in the loss.",
    )
    parser.add_argument(
        "--cycle-weight", type=float, default=DEFAULT_CYCLE_WEIGHT, help="How much the decoded grid's description says."
    )
    parser.add_argument(
        "--prior-warmup",
        type=int,
        default=DEFAULT_PRIOR_WARMUP_STEPS,
        help="Over how many steps the prior's weight climbs to its full value.",
    )
    add_run_arguments(parser)
    parser.set_defaults(
        epochs=DEFAULT_CODEC_EPOCHS, batch=DEFAULT_CODEC_BATCH_SIZE, learning_rate=DEFAULT_CODEC_LEARNING_RATE
    )


def run(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Train one conditioned codec and report where its best epoch was written."""
    # The trainer and the run store are imported here, so parsing arguments and the commands that
    # train nothing stay clear of them.
    # pylint: disable=import-outside-toplevel
    from samplecore.tracking.session import open_run
    from samplemorph.training.codec_data import CodecCorpus
    from samplemorph.training.codec_run import run_codec_training
    from samplemorph.training.runs import RunPlacement

    del connection
    cache = open_grid_cache(grid_cache_directory(config.library_root, name=arguments.cache))
    descriptor = load_descriptor(
        descriptor_path(config.library_root, name=arguments.descriptor), device=torch.device(arguments.device)
    )
    corpus = CodecCorpus(
        cache=cache, library_root=config.library_root, descriptor=descriptor, descriptor_name=arguments.descriptor
    )
    settings = CodecTrainingSettings(
        run=run_settings_from(arguments),
        weights=CodecLossWeights(
            reconstruction=arguments.reconstruction_weight, prior=arguments.prior_weight, cycle=arguments.cycle_weight
        ),
        residual_size=arguments.residual_size,
        width=arguments.width,
        prior_warmup_steps=arguments.prior_warmup,
    )
    _logger.info("Training over %d cached grids with the %s descriptor.", corpus.sample_count, arguments.descriptor)
    with open_run(
        config.library_root,
        recorded=not arguments.no_tracking,
        experiment_name=CODEC_EXPERIMENT_NAME,
        run_name=arguments.codec,
    ) as tracker:
        outcome = run_codec_training(
            corpus,
            settings=settings,
            placement=RunPlacement(
                library_root=config.library_root, model_name=arguments.codec, tracker=tracker, resume=arguments.resume
            ),
        )

    report_outcome(outcome)
