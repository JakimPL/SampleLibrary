from __future__ import annotations

import argparse
import logging
from typing import Final

from sqlalchemy import Connection

from samplecore.cli_parsing import add_subcommand
from samplecore.cli_support import experiment_key
from samplecore.config import LibraryConfig
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplemorph.model_paths import DEFAULT_DESCRIPTOR_NAME, descriptor_path
from samplemorph.training.descriptor_cache import DEFAULT_GRID_CACHE_NAME, grid_cache_directory, open_grid_cache
from samplemorph.training.run_settings import DEFAULT_ACCELERATOR

COMMAND_NAME: Final[str] = "embed"

_logger = logging.getLogger(__name__)


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = add_subcommand(
        commands, COMMAND_NAME, summary="Describe every cached sample with a stored descriptor, as a new experiment."
    )
    parser.add_argument("--cache", type=str, default=DEFAULT_GRID_CACHE_NAME, help="Which grid cache to describe.")
    parser.add_argument(
        "--descriptor", type=str, default=DEFAULT_DESCRIPTOR_NAME, help="Which stored descriptor describes it."
    )
    parser.add_argument("--label", type=str, default=None, help="A note for the resulting experiment, if any.")
    parser.add_argument(
        "--key",
        type=experiment_key,
        default=None,
        help="File the experiment under this key; a key an earlier run filed ends the command with nothing to do.",
    )
    parser.add_argument("--device", type=str, default=DEFAULT_ACCELERATOR, help="Which device the descriptor runs on.")


def run(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Write one experiment of vectors and report which experiment it became.

    A key an earlier run filed names an experiment already holding every vector of its cache, since
    an embedding lands whole, so the command reports it and loads nothing.
    """
    if arguments.key is not None:
        filed = PostgresExperimentRepository(connection).get_by_key(arguments.key)
        if filed is not None:
            _logger.info("Experiment %d already holds the vectors filed under %s.", filed.id, arguments.key)
            return
    # The descriptor's network is imported here, so parsing arguments and the commands that load no
    # network stay clear of torch.
    # pylint: disable=import-outside-toplevel
    import torch

    from samplemorph.descriptors.embedding import EmbeddingFiling, embed_cache
    from samplemorph.descriptors.learned import load_descriptor

    cache = open_grid_cache(grid_cache_directory(config.library_root, name=arguments.cache))
    descriptor = load_descriptor(
        descriptor_path(config.library_root, name=arguments.descriptor), device=torch.device(arguments.device)
    )
    summary = embed_cache(
        connection,
        descriptor=descriptor,
        cache=cache,
        filing=EmbeddingFiling(model_name=arguments.descriptor, label=arguments.label, key=arguments.key),
    )
    _logger.info(
        "Experiment %d holds %d vectors from the %s descriptor over the %s cache.",
        summary.experiment_id,
        summary.sample_count,
        arguments.descriptor,
        arguments.cache,
    )
