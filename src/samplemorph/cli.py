from __future__ import annotations

import argparse
from enum import StrEnum, unique

from samplecore.cli_parsing import command_parser
from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from samplemorph.commands import response
from samplemorph.service import cli as service_cli


@unique
class MorphCommand(StrEnum):
    """What this pipeline does from a shell: writing a morph filter, and serving morphs."""

    RESPONSE = response.COMMAND_NAME
    SERVE = service_cli.COMMAND_NAME


def main(argv: list[str], *, prog: str) -> None:
    """Run one morph command and report the result, with the catalog open for every command that reads it."""
    arguments = parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    command = MorphCommand(arguments.command)
    match command:
        case MorphCommand.SERVE:
            service_cli.run(config, arguments)
        case MorphCommand.RESPONSE:
            with open_catalog_connection(config.database_url) as connection:
                response.run(connection, config, arguments)


def parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(
        prog=prog, description="Serve morphs between two samples over HTTP, and write morph filters."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    response.add_parser(commands)
    service_cli.add_parser(commands)
    return parser.parse_args(argv)
