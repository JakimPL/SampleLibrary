from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Final

from sqlalchemy import Connection

from samplecore.config import LibraryConfig
from samplemorph.commands.draws import require_sample
from samplemorph.pipeline import encode_sample, listening_set_manifest, load_route, render_listening_set
from samplemorph.route_arguments import (
    add_model_argument,
    add_morpher_argument,
    add_vocoder_arguments,
    route_choice_from,
)
from samplemorph.training.run_settings import DEFAULT_ACCELERATOR

COMMAND_NAME: Final[str] = "render"
MANIFEST_NAME: Final[str] = "manifest.json"

_logger = logging.getLogger(__name__)


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser(COMMAND_NAME, help="Render a listening set between two samples.")
    parser.add_argument("--first", type=str, required=True, help="The sample hash the morph starts from.")
    parser.add_argument("--second", type=str, required=True, help="The sample hash the morph arrives at.")
    parser.add_argument("--output", type=str, required=True, help="The directory to write the audio into.")
    add_model_argument(parser)
    add_vocoder_arguments(parser, device_default=DEFAULT_ACCELERATOR)
    add_morpher_argument(parser)


def run(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Render a listening set between two samples through a stored model.

    The two hashes are checked against the catalog before any model loads, so a mistyped hash is
    reported as such rather than as whatever the models had to say first.
    """
    first_sample = require_sample(connection, arguments.first)
    second_sample = require_sample(connection, arguments.second)
    model, route = load_route(config.library_root, route_choice_from(arguments))
    first = encode_sample(
        connection, config.library_root, first_sample, canonicalizer=route.canonicalizer, codec=route.codec
    )
    second = encode_sample(
        connection, config.library_root, second_sample, canonicalizer=route.canonicalizer, codec=route.codec
    )

    output_directory = Path(arguments.output)
    summary = render_listening_set(first, second, route=route, output_directory=output_directory)
    (output_directory / MANIFEST_NAME).write_text(listening_set_manifest(model.description, summary))

    _logger.info(
        "Wrote %d files for %s against %s, %d of them morphs, into %s.",
        len(summary.files),
        summary.first_hash[:12],
        summary.second_hash[:12],
        summary.morph_count,
        output_directory,
    )
