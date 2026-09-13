from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Final

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE, DATABASE_URL_ENVIRONMENT_VARIABLE
from samplelibrary.commands import COMMANDS, Command, CommandGroup

PROGRAM_NAME: Final[str] = "samplelibrary"
COMMAND_METAVAR: Final[str] = "<command>"
CONFIG_OPTION: Final[str] = "--config"

_logger = logging.getLogger(__name__)


def main() -> None:
    """Run the command a shell names, as the `samplelibrary` console entry point."""
    dispatch(sys.argv[1:])


def dispatch(argv: list[str]) -> None:
    """Run the command a command line names, handing that command every argument after its name.

    The command parses those arguments with its own parser, so its help and its errors are its own.
    `--config` reaches the command through the environment, which every process the command starts
    inherits along with it. The file it names supplies the database too, so a sandbox config keeps
    every command on the sandbox whatever `SAMPLELIBRARY_DATABASE_URL` holds.
    """
    parser = _build_parser()
    arguments, command_arguments = parser.parse_known_args(argv)
    command: Command = arguments.command
    _require_arguments_after_command(parser, argv, command_arguments, command_name=command.name)
    if arguments.config is not None:
        os.environ[CONFIG_PATH_ENVIRONMENT_VARIABLE] = str(arguments.config.resolve())
        os.environ.pop(DATABASE_URL_ENVIRONMENT_VARIABLE, None)

    _run_reporting_a_refused_catalog(command, command_arguments, prog=arguments.program)


def _run_reporting_a_refused_catalog(command: Command, argv: list[str], *, prog: str) -> None:
    """Run the command, ending with one message and what to run when the database refuses to connect.

    A worker process's refusal reaches here too, carried back by the run that started it.

    Raises:
        SystemExit: the configured database refused the connection.
    """
    # pylint: disable=import-outside-toplevel
    from sqlalchemy.exc import OperationalError

    try:
        command.run(argv, prog=prog)
    except OperationalError as error:
        from samplecore.storage.cluster.provisioning import headline, is_connection_refusal, server_message

        if not is_connection_refusal(error):
            raise
        _logger.error(
            "Could not reach the catalog: %s\nRun `samplelibrary setup database` to create it, or correct database_url.",
            headline(server_message(error)),
        )
        sys.exit(1)


def _require_arguments_after_command(
    parser: argparse.ArgumentParser, argv: list[str], command_arguments: list[str], *, command_name: str
) -> None:
    """Accept a command's own arguments only where they follow its name, and `--config` only before it.

    Raises:
        SystemExit: an unrecognized argument precedes the command name, or `--config` follows it.
    """
    first_command_argument = len(argv) - len(command_arguments)
    if argv[first_command_argument:] != command_arguments or argv[first_command_argument - 1] != command_name:
        parser.error(f"unrecognized arguments: {' '.join(command_arguments)}; a command's options follow its name")
    if any(argument.split("=")[0] == CONFIG_OPTION for argument in command_arguments):
        parser.error(
            f"{CONFIG_OPTION} goes before the command name: {PROGRAM_NAME} {CONFIG_OPTION} PATH {command_name}"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=PROGRAM_NAME, description="Run one operation on the sample library.")
    parser.add_argument(
        CONFIG_OPTION,
        type=Path,
        default=None,
        help=f"The configuration file to read; ${CONFIG_PATH_ENVIRONMENT_VARIABLE} or config.toml when left out.",
    )
    subparsers = parser.add_subparsers(title="commands", metavar=COMMAND_METAVAR, required=True)
    for entry in COMMANDS:
        match entry:
            case Command():
                _add_command(subparsers, entry)
            case CommandGroup():
                _add_group(subparsers, entry)
    return parser


def _add_group(subparsers: argparse._SubParsersAction[argparse.ArgumentParser], group: CommandGroup) -> None:
    parser = subparsers.add_parser(group.name, help=group.summary, description=group.summary)
    commands = parser.add_subparsers(title="commands", metavar=COMMAND_METAVAR, required=True)
    for command in group.commands:
        _add_command(commands, command)


def _add_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser], command: Command) -> None:
    """Register a command whose parser takes the whole rest of the line, `--help` included."""
    parser = subparsers.add_parser(command.name, help=command.summary, add_help=False)
    parser.set_defaults(command=command, program=parser.prog)
