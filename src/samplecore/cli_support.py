from __future__ import annotations

import argparse
import io
import logging
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Final

from sqlalchemy import Connection

from samplecore.config import ConfigurationError, LibraryConfig, load_config
from samplecore.storage.database import connect

_LOG_FORMAT: Final[str] = "%(asctime)s  %(message)s"
_LOG_DATE_FORMAT: Final[str] = "%H:%M:%S"
_CONFIRM_FLAG_HINT: Final[str] = "Nothing has been changed. Re-run with --confirm to actually do this."

_logger = logging.getLogger(__name__)


def configure_logging() -> None:
    """Set up plain, timestamped status logging for every console entry point.

    INFO and below go to stdout -- the ordinary progress a long-running pipeline stage reports,
    with nothing else to show while it runs. WARNING and above go to stderr, matching the Unix
    convention that stderr carries what went wrong. Replacing the root logger's handlers, rather
    than adding to whatever is already there, keeps a second call (a second CLI invoked in the
    same process, as tests do) from doubling every line instead of just reconfiguring the streams.
    """
    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.addFilter(lambda record: record.levelno < logging.WARNING)
    stdout_handler.setFormatter(formatter)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers = [stdout_handler, stderr_handler]


def configure_console_output_encoding() -> None:
    """Let stdout and stderr substitute an escape for any character the console cannot encode.

    Shared by every console entry point in this project. A narrow console codepage (for example
    Windows' cp1250) cannot represent every character a cataloged module or sample path may
    contain; without this, printing such a path crashes the whole command instead of garbling
    only that one line. Left alone when a stream has been replaced by something other than the
    usual text wrapper, such as a test's captured stream.
    """
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="backslashreplace")
    if isinstance(sys.stderr, io.TextIOWrapper):
        sys.stderr.reconfigure(errors="backslashreplace")


def load_config_or_exit() -> LibraryConfig:
    """Load the library configuration, exiting with a clear message when it cannot be found.

    Shared by every console entry point in this project, so a missing or invalid ``config.toml``
    is reported identically regardless of which one was run. Configures logging itself, rather
    than relying on a caller to have done so first, so the error is visible whenever this function
    is the one reporting it.

    Raises:
        SystemExit: the configuration file is missing or fails validation.
    """
    configure_logging()
    try:
        return load_config()
    except ConfigurationError as error:
        _logger.error("Configuration error: %s", error)
        sys.exit(1)


def bootstrap_cli() -> LibraryConfig:
    """Prepare a console entry point to run, then load its configuration.

    Shared by every console entry point in this project, so setup is identical regardless of
    which one was run.

    Raises:
        SystemExit: the configuration file is missing or fails validation.
    """
    configure_console_output_encoding()
    return load_config_or_exit()


@contextmanager
def open_catalog_connection(database_url: str) -> Iterator[Connection]:
    """Open the catalog for one console entry point's operation, closing it again afterward.

    Shared by every console entry point that needs the catalog open for exactly the duration of
    one call, so this connect/close lifecycle reads identically regardless of which one it is.
    """
    connection = connect(database_url)
    try:
        yield connection
    finally:
        connection.close()


def report_dry_run(description: str) -> None:
    """Log what a confirm-gated destructive script would do, and that nothing has happened yet.

    Shared by every such script's ``main()``, so the "nothing changes without --confirm" contract
    reads identically regardless of which script reports it.
    """
    _logger.info("%s %s", description, _CONFIRM_FLAG_HINT)


def confirmed(
    argv: list[str] | None,
    parse_arguments: Callable[[list[str] | None], argparse.Namespace],
    dry_run_message: str,
) -> bool:
    """Set up logging and parse a confirm-gated script's arguments, reporting when not confirmed.

    Shared by every destructive maintenance script's ``main()``: a false result means ``--confirm``
    was not passed, the dry-run description has already been logged, and the caller's own body
    should simply return without doing anything else. ``parse_arguments`` must produce a namespace
    carrying a ``confirm: bool`` field, matching the ``--confirm`` flag every such script defines.
    """
    configure_logging()
    arguments = parse_arguments(argv)
    if arguments.confirm:
        return True
    report_dry_run(dry_run_message)
    return False
