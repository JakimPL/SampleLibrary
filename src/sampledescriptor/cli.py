from __future__ import annotations

import argparse
import logging
import sys
from enum import StrEnum, unique

from sqlalchemy import Connection

from samplecore.cli_parsing import command_parser
from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from samplecore.config import LibraryConfig
from samplecore.exit_status import ExitStatus
from sampledescriptor.commands import adopt, cache_grids, embed, train_descriptor
from sampledescriptor.pretrained import PretrainedDescriptorMissingError

_logger = logging.getLogger(__name__)


@unique
class DescriptorCommand(StrEnum):
    """What this pipeline does from a shell: one module per command under `sampledescriptor.commands`."""

    CACHE_GRIDS = cache_grids.COMMAND_NAME
    TRAIN = train_descriptor.COMMAND_NAME
    EMBED = embed.COMMAND_NAME
    ADOPT = adopt.COMMAND_NAME


def main(argv: list[str], *, prog: str) -> None:
    """Run one descriptor command and report the result, with the catalog open for the commands that read it.

    Raises:
        SystemExit: the bundled descriptor was asked for and this installation carries none.
    """
    arguments = parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    command = DescriptorCommand(arguments.command)
    match command:
        case DescriptorCommand.ADOPT:
            _adopt(config, arguments)
        case DescriptorCommand.CACHE_GRIDS | DescriptorCommand.TRAIN | DescriptorCommand.EMBED:
            with open_catalog_connection(config.catalog_url()) as connection:
                _run_on_catalog(command, connection, config, arguments)


def _run_on_catalog(
    command: DescriptorCommand, connection: Connection, config: LibraryConfig, arguments: argparse.Namespace
) -> None:
    match command:
        case DescriptorCommand.CACHE_GRIDS:
            cache_grids.run(connection, config, arguments)
        case DescriptorCommand.TRAIN:
            train_descriptor.run(connection, config, arguments)
        case DescriptorCommand.EMBED:
            embed.run(connection, config, arguments)


def _adopt(config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Store the bundled descriptor in the library.

    Raises:
        SystemExit: this installation carries no bundled descriptor.
    """
    try:
        adopt.run(config, arguments)
    except PretrainedDescriptorMissingError as error:
        _logger.error("%s", error)
        sys.exit(ExitStatus.REFUSED)


def parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(
        prog=prog,
        description="Cache the sounds' grids, teach the learned descriptor or adopt the bundled one, "
        "and describe every sample with it.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    cache_grids.add_parser(commands)
    train_descriptor.add_parser(commands)
    embed.add_parser(commands)
    adopt.add_parser(commands)
    return parser.parse_args(argv)
