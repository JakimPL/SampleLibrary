from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Final

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from samplelibrary.commands import COMMANDS, Command, CommandGroup

PROGRAM_NAME: Final[str] = "samplelibrary"
COMMAND_METAVAR: Final[str] = "<command>"


def main() -> None:
    """Run the command a shell names, as the `samplelibrary` console entry point."""
    dispatch(sys.argv[1:])


def dispatch(argv: list[str]) -> None:
    """Run the command a command line names, handing that command every argument after its name.

    The command parses those arguments with its own parser, so its help and its errors are its own.
    `--config` reaches the command through the environment, which every process the command starts
    inherits along with it.
    """
    arguments, command_arguments = _build_parser().parse_known_args(argv)
    if arguments.config is not None:
        os.environ[CONFIG_PATH_ENVIRONMENT_VARIABLE] = str(arguments.config.resolve())

    command: Command = arguments.command
    command.run(command_arguments, prog=arguments.program)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=PROGRAM_NAME, description="Run one operation on the sample library.")
    parser.add_argument(
        "--config",
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
