from __future__ import annotations

import argparse
import io
import logging
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Final

from sqlalchemy import Connection
from sqlalchemy.engine import make_url

from samplecore.config import ConfigurationError, LibraryConfig, load_config
from samplecore.exit_status import ExitStatus
from samplecore.storage.database import connect
from samplecore.storage.sample_audio import SampleAudio

_LOG_FORMAT: Final[str] = "%(asctime)s  %(message)s"
_LOG_DATE_FORMAT: Final[str] = "%H:%M:%S"
_CONFIRM_FLAG_HINT: Final[str] = "Nothing has been changed. Pass --confirm to carry it out."

MINIMUM_PORT: Final[int] = 1
MAXIMUM_PORT: Final[int] = 65_535

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
        sys.exit(ExitStatus.REFUSED)


def bootstrap_cli() -> LibraryConfig:
    """Prepare a console entry point to run, then load its configuration.

    Shared by every console entry point in this project, so setup is identical regardless of
    which one was run.

    Raises:
        SystemExit: the configuration file is missing or fails validation.
    """
    configure_console_output_encoding()
    return load_config_or_exit()


def redact_database_url(database_url: str) -> str:
    """A database URL as it is safe to log, with the password masked.

    Shared by every console entry point that names the database it is about to act on, so a URL
    reaching a console or a captured shell log carries the server, the role, and the database, and
    leaves the credential behind.
    """
    return make_url(database_url).render_as_string()


@contextmanager
def open_catalog_reader(database_url: str) -> Iterator[Connection]:
    """Open the catalog read-only for one console entry point's operation, closing it again afterward.

    For a command that reports what the catalog holds: it attaches to a catalog another process
    prepared, and Postgres refuses any write it attempts.
    """
    connection = connect(database_url, read_only=True)
    try:
        yield connection
    finally:
        connection.close()


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


@contextmanager
def open_catalog_audio(config: LibraryConfig) -> Iterator[tuple[Connection, SampleAudio]]:
    """Open the catalog for one pass over its samples' audio, together with the reader of that audio.

    The reader learns every sample file the catalog lists as the pass opens, so a pass reads each
    sample from the store or from the files cataloged when it started.
    """
    with open_catalog_connection(config.database_url) as connection:
        yield connection, SampleAudio.from_catalog(connection, config.library_root)


@contextmanager
def ending_in_one_line(outcome: str, refusals: tuple[type[ValueError], ...]) -> Iterator[None]:
    """End the process with one message when the work inside is refused, saying what was left undone.

    A refusal is a request this command cannot carry out as asked -- an experiment it cannot resume,
    a file it cannot read as what it names -- which a person fixes in the command line, so it reads
    as one line rather than a traceback.

    Raises:
        SystemExit: one of `refusals` was raised inside.
    """
    try:
        yield
    except refusals as error:
        _logger.error("%s: %s.", outcome, error)
        sys.exit(ExitStatus.REFUSED)


def report_dry_run(description: str) -> None:
    """Log what a confirm-gated destructive command would do, and that it waits for `--confirm`.

    Shared by every such command, so the dry run reads identically whichever command reports it.
    """
    _logger.info("%s %s", description, _CONFIRM_FLAG_HINT)


def integer_at_least(minimum: int) -> Callable[[str], int]:
    """An argparse type reading a whole number no smaller than ``minimum``, reported the way argparse reports its own errors."""
    return lambda raw_value: _bounded_integer(raw_value, minimum=minimum, maximum=None)


def integer_between(minimum: int, maximum: int) -> Callable[[str], int]:
    """An argparse type reading a whole number from ``minimum`` to ``maximum`` inclusive."""
    return lambda raw_value: _bounded_integer(raw_value, minimum=minimum, maximum=maximum)


def positive_multiple_of(step: int) -> Callable[[str], int]:
    """An argparse type reading a whole number of at least ``step`` that ``step`` divides."""

    def read(raw_value: str) -> int:
        value = _bounded_integer(raw_value, minimum=step, maximum=None)
        if value % step:
            raise argparse.ArgumentTypeError(f"must be a multiple of {step}, not {value}")
        return value

    return read


def positive_integer(raw_value: str) -> int:
    """An argparse type reading a count of at least one."""
    return _bounded_integer(raw_value, minimum=1, maximum=None)


def non_negative_integer(raw_value: str) -> int:
    """An argparse type reading a count that may be zero, such as a number of helper processes."""
    return _bounded_integer(raw_value, minimum=0, maximum=None)


def port_number(raw_value: str) -> int:
    """An argparse type reading a TCP port."""
    return _bounded_integer(raw_value, minimum=MINIMUM_PORT, maximum=MAXIMUM_PORT)


def _bounded_integer(raw_value: str, *, minimum: int, maximum: int | None) -> int:
    """Read one option value.

    Raises:
        argparse.ArgumentTypeError: the value is not a whole number, or lies outside the bounds.
    """
    try:
        value = int(raw_value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"expected a whole number, not {raw_value!r}") from error

    if value < minimum:
        raise argparse.ArgumentTypeError(f"must be at least {minimum}, not {value}")
    if maximum is not None and value > maximum:
        raise argparse.ArgumentTypeError(f"must be at most {maximum}, not {value}")
    return value
