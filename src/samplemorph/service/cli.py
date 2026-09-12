from __future__ import annotations

import argparse
from typing import Final
from urllib.parse import urlsplit

import uvicorn

from samplecore.cli_support import bootstrap_cli
from samplecore.config import LibraryConfig
from samplemorph.route_arguments import (
    add_model_argument,
    add_morpher_argument,
    add_vocoder_arguments,
    route_choice_from,
)
from samplemorph.service.app import create_app
from samplemorph.service.settings import DEFAULT_INFERENCE_DEVICE, ServiceSettings

FALLBACK_HOST: Final[str] = "127.0.0.1"
FALLBACK_PORT: Final[int] = 8010


def main(argv: list[str] | None = None) -> None:
    """Serve morphs over HTTP at the address the configuration names, through the models the flags pick."""
    arguments = _parse_arguments(argv)
    config = bootstrap_cli()
    host, port = _bind_address(config, arguments)
    settings = ServiceSettings(library_root=config.library_root, choice=route_choice_from(arguments))
    uvicorn.run(create_app(settings), host=host, port=port)


def _bind_address(config: LibraryConfig, arguments: argparse.Namespace) -> tuple[str, int]:
    """The host and port to bind: the flags first, then the `[inference] url` the API dials."""
    configured = urlsplit(config.inference.url)
    host = arguments.host if arguments.host is not None else (configured.hostname or FALLBACK_HOST)
    port = arguments.port if arguments.port is not None else (configured.port or FALLBACK_PORT)
    return host, port


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve morphs between two samples over HTTP.")
    parser.add_argument("--host", type=str, default=None, help="The address to bind, in place of the configured one.")
    parser.add_argument("--port", type=int, default=None, help="The port to bind, in place of the configured one.")
    add_model_argument(parser)
    add_vocoder_arguments(parser, device_default=DEFAULT_INFERENCE_DEVICE)
    add_morpher_argument(parser)
    return parser.parse_args(argv)
