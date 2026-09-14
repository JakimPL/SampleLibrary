from __future__ import annotations

import argparse
import logging
import sys
from typing import Final

from samplecore.cli_support import port_number
from samplecore.config import LibraryConfig
from samplemorph.route_arguments import (
    add_model_argument,
    add_morpher_argument,
    add_vocoder_arguments,
    route_choice_from,
)
from samplemorph.service.settings import DEFAULT_INFERENCE_DEVICE, ServiceSettings

COMMAND_NAME: Final[str] = "serve"

_logger = logging.getLogger(__name__)


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser(COMMAND_NAME, help="Serve morphs between two samples over HTTP.")
    parser.add_argument("--host", type=str, default=None, help="The address to bind, in place of the configured one.")
    parser.add_argument(
        "--port", type=port_number, default=None, help="The port to bind, in place of the configured one."
    )
    add_model_argument(parser)
    add_vocoder_arguments(parser, device_default=DEFAULT_INFERENCE_DEVICE)
    add_morpher_argument(parser)


def run(config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Load the route the flags pick, then serve morphs over HTTP at the address the configuration names.

    Raises:
        SystemExit: the route cannot be loaded, reported in one line before any address is bound.
    """
    # The server and the networks it loads are imported here, so parsing arguments stays clear of them.
    # pylint: disable=import-outside-toplevel
    import uvicorn

    from samplemorph.pipeline import ModelFileChanged
    from samplemorph.service.app import create_app
    from samplemorph.service.renderer import load_renderer

    host, port = _bind_address(config, arguments)
    settings = ServiceSettings(library_root=config.library_root, choice=route_choice_from(arguments))
    try:
        renderer = load_renderer(settings)
    except (FileNotFoundError, ValueError, ModelFileChanged) as error:
        _logger.error("Serving nothing: %s.", error)
        sys.exit(1)

    uvicorn.run(create_app(renderer), host=host, port=port)


def _bind_address(config: LibraryConfig, arguments: argparse.Namespace) -> tuple[str, int]:
    """The host and port to bind: the flags first, then the `[inference] url` the API dials."""
    host = arguments.host if arguments.host is not None else config.inference.host
    port = arguments.port if arguments.port is not None else config.inference.port
    return host, port
