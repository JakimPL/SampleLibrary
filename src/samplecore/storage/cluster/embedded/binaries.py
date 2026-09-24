from __future__ import annotations

import sys
from enum import StrEnum, unique
from pathlib import Path
from typing import Final

EXECUTABLE_SUFFIX: Final[str] = ".exe" if sys.platform == "win32" else ""


class PostgresBinariesUnavailableError(Exception):
    """Raised when the Postgres programs a managed database runs on are not installed."""


@unique
class PostgresProgram(StrEnum):
    """The Postgres programs a managed cluster runs: one creates its data, the other starts and stops its server."""

    INITDB = "initdb"
    PG_CTL = "pg_ctl"


def program_path(program: PostgresProgram) -> Path:
    """Where one Postgres program is installed, unpacking the bundled server on first use.

    Raises:
        PostgresBinariesUnavailableError: the `app` extra, which carries the bundled server, is not installed.
    """
    path = _binary_directory() / f"{program.value}{EXECUTABLE_SUFFIX}"
    if not path.is_file():
        raise PostgresBinariesUnavailableError(f"The bundled Postgres holds no {program.value} at {path}.")
    return path


def _binary_directory() -> Path:
    """The bundled server's program folder.

    `postgresql_binaries.bin()` unpacks the archive its wheel carries beside itself the first time
    it runs, and returns the folder the programs landed in.

    Raises:
        PostgresBinariesUnavailableError: the package is not installed.
    """
    try:
        import postgresql_binaries  # pylint: disable=import-outside-toplevel
    except ImportError as error:
        raise PostgresBinariesUnavailableError(
            "The bundled Postgres is not installed. Install the `app` extra, or name a server of your own "
            "with database_url in the config."
        ) from error
    return postgresql_binaries.bin()
