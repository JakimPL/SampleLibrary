from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Final

from sqlalchemy import Connection

from samplecore.cli_parsing import add_subcommand
from samplecore.config import LibraryConfig
from samplecore.exit_status import ExitStatus
from samplecore.storage.sample_audio import SampleAudio, SampleUnavailableError
from samplemorph.commands.draws import SampleNotCataloged, require_sample
from samplemorph.pipeline import (
    encode_pair,
    listening_set_manifest,
    load_route,
    read_heard_sample,
    render_listening_set,
)
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
    parser = add_subcommand(commands, COMMAND_NAME, summary="Render a listening set between two samples.")
    parser.add_argument("--first", type=str, required=True, help="The sample hash the morph starts from.")
    parser.add_argument("--second", type=str, required=True, help="The sample hash the morph arrives at.")
    parser.add_argument("--output", type=str, required=True, help="The directory to write the audio into.")
    add_model_argument(parser)
    add_vocoder_arguments(parser, device_default=DEFAULT_ACCELERATOR)
    add_morpher_argument(parser)


def run(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Render a listening set between two samples through a stored model.

    Both samples are read before any model loads, so a mistyped hash, or a sample whose files are
    gone, is reported as such, in one line, rather than as whatever the models had to say first.

    Raises:
        SystemExit: either hash names no cataloged sample, or a sample none of whose files holds it now.
    """
    audio = SampleAudio.from_catalog(connection, config.library_root)
    try:
        first = read_heard_sample(connection, audio, require_sample(connection, arguments.first))
        second = read_heard_sample(connection, audio, require_sample(connection, arguments.second))
    except (SampleNotCataloged, SampleUnavailableError) as error:
        _logger.error("Rendered nothing: %s.", error)
        sys.exit(ExitStatus.REFUSED)
    loaded = load_route(config.library_root, route_choice_from(arguments))
    pair = encode_pair(
        first,
        second,
        canonicalizer=loaded.route.canonicalizer,
        codec=loaded.route.codec,
    )

    output_directory = Path(arguments.output)
    summary = render_listening_set(pair, route=loaded.route, output_directory=output_directory)
    (output_directory / MANIFEST_NAME).write_text(listening_set_manifest(loaded, summary))

    _logger.info(
        "Wrote %d files for %s against %s, %d of them morphs, into %s.",
        len(summary.files),
        summary.first_hash[:12],
        summary.second_hash[:12],
        summary.morph_count,
        output_directory,
    )
