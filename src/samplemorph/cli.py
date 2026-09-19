from __future__ import annotations

import argparse
from collections.abc import Callable
from enum import StrEnum, unique
from typing import Final

from sqlalchemy import Connection

from samplecore.cli_parsing import command_parser
from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from samplecore.config import LibraryConfig
from samplemorph.commands import (
    cache_grids,
    compare,
    draw_pairs,
    embed,
    fit,
    measure,
    publish,
    read_ladders,
    render,
    response,
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
    DRAW_PAIRS = draw_pairs.COMMAND_NAME
    COMPARE = compare.COMMAND_NAME
    READ_LADDERS = read_ladders.COMMAND_NAME
    RESPONSE = response.COMMAND_NAME
    PUBLISH = publish.COMMAND_NAME
    SERVE = service_cli.COMMAND_NAME


CATALOG_COMMANDS: Final[dict[MorphCommand, CatalogCommand]] = {
    MorphCommand.FIT: fit.run,
    MorphCommand.CACHE_GRIDS: cache_grids.run,
    MorphCommand.TRAIN_DESCRIPTOR: train_descriptor.run,
    MorphCommand.EMBED: embed.run,
    MorphCommand.TRAIN_CODEC: train_codec.run,
    MorphCommand.TRAIN_RESTORER: train_restorer.run,
    MorphCommand.RENDER: render.run,
    MorphCommand.MEASURE: measure.run,
    MorphCommand.DRAW_PAIRS: draw_pairs.run,
    MorphCommand.COMPARE: compare.run,
    MorphCommand.READ_LADDERS: read_ladders.run,
    MorphCommand.RESPONSE: response.run,
}


def main(argv: list[str], *, prog: str) -> None:
    """Run one morph command and report the result, with the catalog open for every command that reads it."""
    arguments = parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    command = MorphCommand(arguments.command)
    match command:
        case MorphCommand.SERVE:
            service_cli.run(config, arguments)
        case MorphCommand.PUBLISH:
            publish.run(config, arguments)
        case _:
            with open_catalog_connection(config.database_url) as connection:
                CATALOG_COMMANDS[command](connection, config, arguments)


def parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
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
    draw_pairs.add_parser(commands)
    compare.add_parser(commands)
    read_ladders.add_parser(commands)
    response.add_parser(commands)
    publish.add_parser(commands)
    service_cli.add_parser(commands)
    return parser.parse_args(argv)
