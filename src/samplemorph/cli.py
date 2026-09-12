from __future__ import annotations

import argparse
from enum import StrEnum, unique

from samplecore.cli_support import bootstrap_cli, open_catalog_connection
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


@unique
class MorphCommand(StrEnum):
    """What this pipeline does from a shell, one module per command under `samplemorph.commands`."""

    FIT = fit.COMMAND_NAME
    CACHE_GRIDS = cache_grids.COMMAND_NAME
    TRAIN_DESCRIPTOR = train_descriptor.COMMAND_NAME
    EMBED = embed.COMMAND_NAME
    TRAIN_CODEC = train_codec.COMMAND_NAME
    TRAIN_RESTORER = train_restorer.COMMAND_NAME
    RENDER = render.COMMAND_NAME
    MEASURE = measure.COMMAND_NAME


def main(argv: list[str] | None = None) -> None:
    """Run one morph command against the library and report the result."""
    arguments = _parse_arguments(argv)
    config = bootstrap_cli()
    with open_catalog_connection(config.database_url) as connection:
        match MorphCommand(arguments.command):
            case MorphCommand.FIT:
                fit.run(connection, config, arguments)
            case MorphCommand.CACHE_GRIDS:
                cache_grids.run(connection, config, arguments)
            case MorphCommand.TRAIN_DESCRIPTOR:
                train_descriptor.run(connection, config, arguments)
            case MorphCommand.EMBED:
                embed.run(connection, config, arguments)
            case MorphCommand.TRAIN_CODEC:
                train_codec.run(connection, config, arguments)
            case MorphCommand.TRAIN_RESTORER:
                train_restorer.run(connection, config, arguments)
            case MorphCommand.RENDER:
                render.run(connection, config, arguments)
            case MorphCommand.MEASURE:
                measure.run(connection, config, arguments)


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fit a decodable sample codec, and render morphs through it.")
    commands = parser.add_subparsers(dest="command", required=True)
    fit.add_parser(commands)
    cache_grids.add_parser(commands)
    train_descriptor.add_parser(commands)
    embed.add_parser(commands)
    train_codec.add_parser(commands)
    train_restorer.add_parser(commands)
    render.add_parser(commands)
    measure.add_parser(commands)
    return parser.parse_args(argv)
