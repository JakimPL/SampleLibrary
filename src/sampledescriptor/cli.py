from __future__ import annotations

import argparse
from enum import StrEnum, unique

from samplecore.cli_parsing import command_parser
from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from sampledescriptor.commands import cache_grids, embed, train_descriptor


@unique
class DescriptorCommand(StrEnum):
    """What this pipeline does from a shell: one module per command under `sampledescriptor.commands`."""

    CACHE_GRIDS = cache_grids.COMMAND_NAME
    TRAIN = train_descriptor.COMMAND_NAME
    EMBED = embed.COMMAND_NAME


def main(argv: list[str], *, prog: str) -> None:
    """Run one descriptor command and report the result, with the catalog open for it."""
    arguments = parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    command = DescriptorCommand(arguments.command)
    with open_catalog_connection(config.catalog_url()) as connection:
        match command:
            case DescriptorCommand.CACHE_GRIDS:
                cache_grids.run(connection, config, arguments)
            case DescriptorCommand.TRAIN:
                train_descriptor.run(connection, config, arguments)
            case DescriptorCommand.EMBED:
                embed.run(connection, config, arguments)


def parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(
        prog=prog,
        description="Cache the sounds' grids, teach the learned descriptor, and describe every sample with it.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    cache_grids.add_parser(commands)
    train_descriptor.add_parser(commands)
    embed.add_parser(commands)
    return parser.parse_args(argv)
