from __future__ import annotations

import argparse
import logging
from typing import Final

from sqlalchemy import Connection

from samplecore.cli_parsing import add_subcommand
from samplecore.cli_support import non_negative_integer, positive_integer
from samplecore.config import LibraryConfig
from samplecore.storage.sample_audio import SampleAudio
from samplemorph.commands.draws import add_canonicalizer_argument, draw_cached_samples
from samplemorph.descriptors.pooling import DESCRIPTOR_BANDS_PER_SEMITONE
from samplemorph.registries import CANONICALIZER_REGISTRY
from samplemorph.training.descriptor_cache import (
    DEFAULT_GRID_CACHE_NAME,
    DEFAULT_RETUNED_VIEW_COUNT,
    DEFAULT_VIEW_RANGE_SEMITONES,
    GridCacheRecipe,
    build_grid_cache,
    grid_cache_directory,
)
from samplemorph.training.run_settings import DEFAULT_RANDOM_SEED, DEFAULT_WORKER_COUNT

COMMAND_NAME: Final[str] = "cache-grids"

_logger = logging.getLogger(__name__)


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = add_subcommand(
        commands,
        COMMAND_NAME,
        summary="Canonicalize a draw of the library once, with retuned views, for training a descriptor.",
    )
    parser.add_argument("--cache", type=str, default=DEFAULT_GRID_CACHE_NAME, help="The name to store the cache under.")
    add_canonicalizer_argument(
        parser, help_text="Which frequency axis to canonicalize onto.", names=CANONICALIZER_REGISTRY
    )
    parser.add_argument(
        "--samples", type=positive_integer, default=None, help="How many samples to draw; every sample when left out."
    )
    parser.add_argument(
        "--bands-per-semitone",
        type=positive_integer,
        default=DESCRIPTOR_BANDS_PER_SEMITONE,
        help="How finely the band axis is kept once pooled.",
    )
    parser.add_argument(
        "--views",
        type=non_negative_integer,
        default=DEFAULT_RETUNED_VIEW_COUNT,
        help="How many retuned readings each sample gets.",
    )
    parser.add_argument(
        "--range",
        type=float,
        default=DEFAULT_VIEW_RANGE_SEMITONES,
        help="How far, in semitones either way, a retuned reading may sit.",
    )
    parser.add_argument(
        "--workers", type=non_negative_integer, default=DEFAULT_WORKER_COUNT, help="How many processes canonicalize."
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED, help="The seed the draw and the views use.")


def run(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Build one named grid cache over a draw of the catalog and report where it went."""
    audio = SampleAudio.from_catalog(connection, config.library_root)
    samples = draw_cached_samples(connection, audio, count=arguments.samples, random_seed=arguments.seed)
    recipe = GridCacheRecipe(
        canonicalizer_name=arguments.canonicalizer,
        anchor=arguments.anchor,
        bands_per_semitone=arguments.bands_per_semitone,
        view_count=arguments.views,
        view_range_semitones=arguments.range,
        random_seed=arguments.seed,
    )
    directory = grid_cache_directory(config.library_root, name=arguments.cache)
    _logger.info(
        "Canonicalizing %d samples with %d retuned views each into %s...", len(samples), arguments.views, directory
    )
    cache = build_grid_cache(directory, samples=samples, audio=audio, recipe=recipe, worker_count=arguments.workers)
    _logger.info(
        "Cached %d samples as %d x %d grids, %.1f GB on disk.",
        cache.sample_count,
        cache.description.band_count,
        cache.description.time_columns,
        cache.grids.nbytes / 1e9,
    )
