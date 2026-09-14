from __future__ import annotations

import argparse
from collections.abc import Callable
from enum import StrEnum, unique

from sqlalchemy import Connection

from samplecore.cli_parsing import command_parser
from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from samplecore.config import LibraryConfig
from samplemorph.commands import (
    cache_grids,
    embed,
    fit,
    measure,
    render,
    train_codec,
    train_descriptor,
    train_restorer,
)
from samplemorph.service import cli as service_cli

CatalogCommand = Callable[[Connection, LibraryConfig, argparse.Namespace], None]


@unique
class MorphCommand(StrEnum):
    """What this pipeline does from a shell: one module per command under `samplemorph.commands`, and serving."""

    FIT = fit.COMMAND_NAME
    CACHE_GRIDS = cache_grids.COMMAND_NAME
    TRAIN_DESCRIPTOR = train_descriptor.COMMAND_NAME
    EMBED = embed.COMMAND_NAME
    TRAIN_CODEC = train_codec.COMMAND_NAME
    TRAIN_RESTORER = train_restorer.COMMAND_NAME
    RENDER = render.COMMAND_NAME
    MEASURE = measure.COMMAND_NAME
    SERVE = service_cli.COMMAND_NAME


def main(argv: list[str], *, prog: str) -> None:
    """Run one morph command and report the result, with the catalog open for every command that reads it."""
    arguments = _parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    match MorphCommand(arguments.command):
        case MorphCommand.SERVE:
            service_cli.run(config, arguments)
        case MorphCommand.FIT:
            _on_catalog(fit.run, config, arguments)
        case MorphCommand.CACHE_GRIDS:
            _on_catalog(cache_grids.run, config, arguments)
        case MorphCommand.TRAIN_DESCRIPTOR:
            _on_catalog(train_descriptor.run, config, arguments)
        case MorphCommand.EMBED:
            _on_catalog(embed.run, config, arguments)
        case MorphCommand.TRAIN_CODEC:
            _on_catalog(train_codec.run, config, arguments)
        case MorphCommand.TRAIN_RESTORER:
            _on_catalog(train_restorer.run, config, arguments)
        case MorphCommand.RENDER:
            _on_catalog(render.run, config, arguments)
        case MorphCommand.MEASURE:
            _on_catalog(measure.run, config, arguments)


def _on_catalog(run: CatalogCommand, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    with open_catalog_connection(config.database_url) as connection:
        run(connection, config, arguments)


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(
        prog=prog, description="Fit, train and render the decodable representation, and serve morphs over HTTP."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    fit.add_parser(commands)
    cache_grids.add_parser(commands)
    train_descriptor.add_parser(commands)
    embed.add_parser(commands)
    train_codec.add_parser(commands)
    train_restorer.add_parser(commands)
    render.add_parser(commands)
    measure.add_parser(commands)
    service_cli.add_parser(commands)
    return parser.parse_args(argv)
