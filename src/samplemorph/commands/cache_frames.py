from __future__ import annotations

import argparse
import logging
from typing import Final

from sqlalchemy import Connection

from samplecore.cli_parsing import add_subcommand
from samplecore.cli_support import non_negative_integer, positive_integer
from samplecore.config import LibraryConfig
from samplecore.storage.sample_audio import SampleAudio
from samplemorph.commands.draws import draw_cached_samples
from samplemorph.coordinates.frames import frame_analysis
from samplemorph.training.frame_cache import (
    DEFAULT_FRAME_CACHE_NAME,
    DEFAULT_RETUNING_RANGE_SEMITONES,
    FrameCacheRecipe,
    build_frame_cache,
    frame_cache_directory,
)
from samplemorph.training.run_settings import DEFAULT_RANDOM_SEED, DEFAULT_WORKER_COUNT

COMMAND_NAME: Final[str] = "cache-frames"

_logger = logging.getLogger(__name__)


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = add_subcommand(
        commands,
        COMMAND_NAME,
        summary="Read a draw of the library once as constant-Q frames, as stored and truly retuned, for a pitch head.",
    )
    parser.add_argument(
        "--cache", type=str, default=DEFAULT_FRAME_CACHE_NAME, help="The name to store the frame cache under."
    )
    parser.add_argument(
        "--samples", type=positive_integer, default=None, help="How many samples to draw; every sample when left out."
    )
    parser.add_argument(
        "--range",
        type=float,
        default=DEFAULT_RETUNING_RANGE_SEMITONES,
        help="How far, in semitones either way, the retuned reading may sit.",
    )
    parser.add_argument(
        "--workers", type=non_negative_integer, default=DEFAULT_WORKER_COUNT, help="How many processes read frames."
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED, help="The seed the draw and the offsets use.")


def run(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Build one named frame cache over a draw of the catalog and report where it went."""
    audio = SampleAudio.from_catalog(connection, config.library_root)
    samples = draw_cached_samples(connection, audio, count=arguments.samples, random_seed=arguments.seed)
    recipe = FrameCacheRecipe(
        analysis=frame_analysis(), retuning_range_semitones=arguments.range, random_seed=arguments.seed
    )
    directory = frame_cache_directory(config.library_root, name=arguments.cache)
    _logger.info("Reading %d samples as constant-Q frames, each once retuned, into %s...", len(samples), directory)
    cache = build_frame_cache(directory, samples=samples, audio=audio, recipe=recipe, worker_count=arguments.workers)
    _logger.info(
        "Cached %d samples as up to %d frames of %d bands each, %.1f GB on disk.",
        cache.sample_count,
        cache.description.analysis.kept_frame_count,
        cache.description.analysis.band_count,
        cache.frames.nbytes / 1e9,
    )
