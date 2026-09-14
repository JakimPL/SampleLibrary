from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

from samplecore.cli_parsing import command_parser
from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE, DATABASE_URL_ENVIRONMENT_VARIABLE
from samplecore.exit_status import ExitStatus
from samplelibrary.commands import COMMANDS, Command, CommandGroup
from samplelibrary.environment import (
    CONFIG_OPTION,
    MEMORY_CAP_OPTION,
    MEMORY_SCOPE_OPTION,
    PACKAGE_NAME,
    STEP_LOCK_ENVIRONMENT_VARIABLE,
)

if TYPE_CHECKING:
    from sqlalchemy import Connection

    from samplelibrary.limits.scope import MemoryScope

PROGRAM_NAME: Final[str] = "samplelibrary"
COMMAND_METAVAR: Final[str] = "<command>"
GLOBAL_OPTIONS: Final[tuple[str, ...]] = (CONFIG_OPTION, MEMORY_CAP_OPTION, MEMORY_SCOPE_OPTION)

_logger = logging.getLogger(__name__)


def main() -> None:
    """Run the command a shell names, as the `samplelibrary` console entry point."""
    dispatch(sys.argv[1:])


def dispatch(argv: list[str]) -> None:
    """Run the command a command line names, handing that command every argument after its name.

    The command parses those arguments with its own parser, so its help and its errors are its own.
    `--config` reaches the command through the environment, which every process the command starts
    inherits along with it. The file it names supplies the database too, so a sandbox config keeps
    every command on the sandbox whatever `SAMPLELIBRARY_DATABASE_URL` holds. `--memory-cap` holds
    the command, and everything it starts, to a memory ceiling before it loads anything of its own.
    """
    parser = _build_parser()
    arguments, command_arguments = parser.parse_known_args(argv)
    command: Command = arguments.command
    _require_arguments_after_command(
        parser, argv, command_arguments, command_name=command.name, command_path=arguments.program
    )
    if arguments.config is not None:
        os.environ[CONFIG_PATH_ENVIRONMENT_VARIABLE] = str(arguments.config.resolve())
        os.environ.pop(DATABASE_URL_ENVIRONMENT_VARIABLE, None)

    scope = _entered_memory_scope(arguments.memory_cap, arguments.memory_scope, argv)
    _run_reporting_an_unreachable_catalog(command, command_arguments, prog=arguments.program, scope=scope)


def _run_reporting_an_unreachable_catalog(
    command: Command, argv: list[str], *, prog: str, scope: MemoryScope | None
) -> None:
    """Run the command, ending with one message and what to check when the database cannot be reached.

    A worker process's failure to connect reaches here too, carried back by the run that started it.
    A command run under a memory ceiling reports what it held at its peak, and ends as a run that
    outgrew its ceiling where anything under it was stopped for holding too much.

    Raises:
        SystemExit: no connection to the configured database could be opened, or the memory ceiling was reached.
    """
    # pylint: disable=import-outside-toplevel
    from sqlalchemy.exc import OperationalError

    try:
        step_lock = _hold_step_lock_when_named()
        command.run(argv, prog=prog)
        if step_lock is not None:
            step_lock.close()
    except MemoryError:
        _logger.error("Ran out of memory%s.", " under the memory ceiling" if scope is not None else "")
        sys.exit(ExitStatus.MEMORY_CAP_REACHED)
    except OperationalError as error:
        from samplecore.storage.cluster.provisioning import headline, is_connection_failure, server_message

        if not is_connection_failure(error):
            raise
        _logger.error(
            "Could not reach the catalog: %s\nCheck that PostgreSQL is running and that database_url names it; "
            "`samplelibrary setup database` creates a missing database.",
            headline(server_message(error)),
        )
        sys.exit(ExitStatus.FAILED)

    if scope is not None:
        _report_the_memory_scope(scope)


def _entered_memory_scope(ceiling_value: str | None, scope_name: str | None, argv: list[str]) -> MemoryScope | None:
    """Hold this process to the ceiling a command line names, starting it again inside one where that is how it is held.

    A command naming no ceiling loads none of this, so a run by hand keeps needing nothing of it, and
    one naming none in words runs as any process does, reporting nothing about memory afterwards.

    Raises:
        SystemExit: the ceiling is written some other way than this project reads, or this system
            cannot hold a process to one.
    """
    if ceiling_value is None:
        return None
    # pylint: disable=import-outside-toplevel
    from samplecore.cli_support import configure_logging
    from samplelibrary.limits.ceiling import MalformedCeiling, MemoryCeiling
    from samplelibrary.limits.probe import memory_scope
    from samplelibrary.limits.scope import MemoryScopeUnavailable

    configure_logging()
    scope = memory_scope()
    try:
        ceiling = MemoryCeiling.parse(ceiling_value)
        if not ceiling.enforced:
            return None
        name = scope_name if scope_name is not None else f"{PROGRAM_NAME}-{os.getpid()}"
        scope.enter(name, ceiling, [sys.executable, "-m", PACKAGE_NAME, *argv])
    except (MalformedCeiling, MemoryScopeUnavailable) as error:
        _logger.error("Ran nothing: %s.", error)
        sys.exit(ExitStatus.REFUSED)
    return scope


def _report_the_memory_scope(scope: MemoryScope) -> None:
    """Say what a capped run held at its peak, and end it as one that outgrew its ceiling where it did.

    Raises:
        SystemExit: something under the ceiling was stopped for holding too much memory.
    """
    peak = scope.peak_bytes()
    if peak is not None:
        _logger.info("Held at most %.2f GB under the memory ceiling.", peak / 1e9)
    if scope.reached_the_ceiling():
        _logger.error("Reached the memory ceiling: a process under it was stopped for holding too much.")
        sys.exit(ExitStatus.MEMORY_CAP_REACHED)


def _hold_step_lock_when_named() -> Connection | None:
    """The connection holding the lock a pipeline names for this process, imported only when one is named.

    A command run by hand names no lock, so it keeps loading nothing beyond its own package.
    """
    if not os.environ.get(STEP_LOCK_ENVIRONMENT_VARIABLE):
        return None
    # pylint: disable-next=import-outside-toplevel
    from samplelibrary.step_lock import hold_step_lock

    return hold_step_lock()


def _require_arguments_after_command(
    parser: argparse.ArgumentParser,
    argv: list[str],
    command_arguments: list[str],
    *,
    command_name: str,
    command_path: str,
) -> None:
    """Accept a command's own arguments only where they follow its name, and this line's own options only before it.

    Raises:
        SystemExit: an unrecognized argument precedes the command name, or an option of this line follows it.
    """
    first_command_argument = len(argv) - len(command_arguments)
    if argv[first_command_argument:] != command_arguments or argv[first_command_argument - 1] != command_name:
        parser.error(f"unrecognized arguments: {' '.join(command_arguments)}; a command's options follow its name")
    misplaced = [
        option for option in GLOBAL_OPTIONS if any(argument.split("=")[0] == option for argument in command_arguments)
    ]
    if misplaced:
        command_words = command_path.removeprefix(PROGRAM_NAME).strip()
        parser.error(
            f"{misplaced[0]} goes before the command name: {PROGRAM_NAME} {misplaced[0]} VALUE {command_words}"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = command_parser(prog=PROGRAM_NAME, description="Run one operation on the sample library.")
    parser.add_argument(
        CONFIG_OPTION,
        type=Path,
        default=None,
        help=f"The configuration file to read; ${CONFIG_PATH_ENVIRONMENT_VARIABLE} or config.toml when left out.",
    )
    parser.add_argument(
        MEMORY_CAP_OPTION,
        type=str,
        default=None,
        help="Hold this command and everything it starts to a memory ceiling, such as 16G, or none.",
    )
    parser.add_argument(
        MEMORY_SCOPE_OPTION,
        type=str,
        default=None,
        help="The name the ceiling holds this command under, which another process finds it running by.",
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
