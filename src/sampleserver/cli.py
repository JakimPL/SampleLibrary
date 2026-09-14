from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Final

import uvicorn

from samplecore.cli_parsing import command_parser
from samplecore.cli_support import bootstrap_cli, open_catalog_connection, port_number, positive_integer
from sampleserver.frontend import (
    FRONTEND_DIRECTORY_ENVIRONMENT_VARIABLE,
    built_frontend,
    frontend_directory_from_environment,
)

APPLICATION_PATH: Final[str] = "sampleserver.main:app"
SOURCE_DIRECTORY: Final[Path] = Path(__file__).resolve().parents[1]
DEFAULT_HOST: Final[str] = "127.0.0.1"
DEFAULT_PORT: Final[int] = 8000
WORKER_COUNT_ENVIRONMENT_VARIABLE: Final[str] = "WEB_CONCURRENCY"


def main(argv: list[str], *, prog: str) -> None:
    """Serve the API, and the built frontend when named, over HTTP once the configuration loads and the catalog answers.

    uvicorn imports the app by its path in every process it starts, so each worker, and each
    restart under `--reload`, reads the configuration afresh and finds the frontend through the
    environment. Checking the configuration and the catalog here first stops a broken start before
    any worker runs, and prepares the catalog's schema once, under its lock.
    """
    arguments = _parse_arguments(argv, prog=prog)
    if arguments.frontend is not None:
        os.environ[FRONTEND_DIRECTORY_ENVIRONMENT_VARIABLE] = str(arguments.frontend)
    config = bootstrap_cli()
    with open_catalog_connection(config.database_url):
        pass

    uvicorn.run(
        APPLICATION_PATH,
        host=arguments.host,
        port=arguments.port,
        reload=arguments.reload,
        reload_dirs=[str(SOURCE_DIRECTORY)] if arguments.reload else None,
        workers=arguments.workers,
    )


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(
        prog=prog, description="Serve the library's API, and the built frontend when named, over HTTP."
    )
    parser.add_argument("--host", type=str, default=DEFAULT_HOST, help="The address to bind.")
    parser.add_argument("--port", type=port_number, default=DEFAULT_PORT, help="The port to bind.")
    processes = parser.add_mutually_exclusive_group()
    processes.add_argument(
        "--reload", action="store_true", help="Restart the server whenever a Python source file changes."
    )
    processes.add_argument(
        "--workers",
        type=positive_integer,
        default=None,
        help="How many processes serve requests side by side; $WEB_CONCURRENCY, or one, when left out.",
    )
    parser.add_argument(
        "--frontend",
        type=Path,
        default=None,
        help="The built frontend to serve beside the API, such as frontend/dist after `npm run build`.",
    )
    arguments = parser.parse_args(argv)
    try:
        arguments.frontend = (
            built_frontend(arguments.frontend)
            if arguments.frontend is not None
            else frontend_directory_from_environment()
        )
    except ValueError as error:
        parser.error(f"--frontend names no built frontend: {error}")
    if arguments.workers is None and not _names_a_process_count(os.environ.get(WORKER_COUNT_ENVIRONMENT_VARIABLE)):
        parser.error(
            f"${WORKER_COUNT_ENVIRONMENT_VARIABLE} names no process count; set it to a whole number of at least 1"
        )
    return arguments


def _names_a_process_count(raw_value: str | None) -> bool:
    """Whether the variable uvicorn reads a process count from is unset, or holds a count it can start."""
    if raw_value is None:
        return True
    try:
        return positive_integer(raw_value) >= 1
    except argparse.ArgumentTypeError:
        return False
