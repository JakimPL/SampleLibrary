from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Final

import uvicorn

from samplecore.cli_parsing import command_parser
from samplecore.cli_support import bootstrap_cli, open_catalog_reader, port_number, positive_integer
from samplecore.config import LibraryConfig, ServiceRoleUnconfiguredError
from samplecore.exit_status import ExitStatus
from samplecore.models.service_role import ServiceRole
from samplecore.paths import PACKAGES_DIRECTORY
from samplecore.storage.cluster.embedded.state import ManagedClusterMissingError
from samplecore.storage.service_roles import ServiceRoleRefusedError, check_service_role
from sampleserver.frontend import (
    FRONTEND_DIRECTORY_ENVIRONMENT_VARIABLE,
    built_frontend,
    frontend_directory_from_environment,
)
from sampleserver.messages import HOST_BEYOND_EXPOSURE, SERVE_REFUSES_PUBLIC
from sampleserver.policy import ServingPolicy

APPLICATION_PATH: Final[str] = "sampleserver.main:app"
DEFAULT_HOST: Final[str] = "127.0.0.1"
DEFAULT_PORT: Final[int] = 8000
WORKER_COUNT_ENVIRONMENT_VARIABLE: Final[str] = "WEB_CONCURRENCY"
NO_WEBSOCKETS: Final[str] = "none"

_logger = logging.getLogger(__name__)


def main(argv: list[str], *, prog: str) -> None:
    """Serve the API read-only, and the built frontend when named, once the catalog answers to a reader's role.

    uvicorn imports the app by its path in every process it starts, so each worker, and each
    restart under `--reload`, reads the configuration afresh and finds the frontend through the
    environment. Checking the reader's role here first stops a start before any worker runs, when the
    role is missing, may change anything, or finds no catalog prepared.

    Raises:
        SystemExit: the config serves the library publicly or on this computer alone while ``--host``
            names another address, names no reader, or the role it names is refused.
    """
    arguments = _parse_arguments(argv, prog=prog)
    if arguments.frontend is not None:
        os.environ[FRONTEND_DIRECTORY_ENVIRONMENT_VARIABLE] = str(arguments.frontend)
    config = bootstrap_cli()
    _admit_exposure(ServingPolicy.of(config.server), host=arguments.host)
    admit_reader(config)
    run_server(host=arguments.host, port=arguments.port, reload=arguments.reload, workers=arguments.workers)


def run_server(*, host: str, port: int, reload: bool, workers: int | None) -> None:
    """Serve the app `sampleserver.main` builds from the configuration, until the server is stopped.

    uvicorn names itself in no header, reads no forwarding header (a site reads the address its
    platform names itself, `sampleserver.visitors`), and speaks no WebSocket, which no route offers.
    ``workers`` left out leaves the count to ``$WEB_CONCURRENCY``, which uvicorn reads.
    """
    uvicorn.run(
        APPLICATION_PATH,
        host=host,
        port=port,
        reload=reload,
        reload_dirs=[str(PACKAGES_DIRECTORY)] if reload else None,
        workers=workers,
        server_header=False,
        proxy_headers=False,
        ws=NO_WEBSOCKETS,
    )


def _admit_exposure(policy: ServingPolicy, *, host: str) -> None:
    """Insist that this command may serve the library the way its config exposes it, on the address asked for.

    Raises:
        SystemExit: the library is exposed to anyone, which `sampleripper site` serves, or ``host``
            lies beyond where the exposure listens.
    """
    if not policy.permits_serve:
        _logger.error("%s", SERVE_REFUSES_PUBLIC)
        sys.exit(ExitStatus.REFUSED)
    if not policy.binds(host):
        _logger.error("%s", HOST_BEYOND_EXPOSURE)
        sys.exit(ExitStatus.REFUSED)


def admit_reader(config: LibraryConfig) -> None:
    """Insist that the role the served API connects as reads the catalog and may change nothing.

    Raises:
        SystemExit: the config names no reader, or the role it names is refused.
    """
    try:
        reader_url = config.service_url(ServiceRole.READER)
    except (ServiceRoleUnconfiguredError, ManagedClusterMissingError) as error:
        _logger.error("%s", error)
        sys.exit(ExitStatus.REFUSED)
    with open_catalog_reader(reader_url) as connection:
        try:
            check_service_role(connection, ServiceRole.READER)
        except ServiceRoleRefusedError as error:
            _logger.error(
                "%s Name a role that reads alone in server_database_url, then run `sampleripper setup database`.",
                error,
            )
            sys.exit(ExitStatus.REFUSED)


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
        help="The built frontend to serve beside the API, such as build/frontend after `just frontend-build`.",
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
    if arguments.workers is None and not names_a_process_count(os.environ.get(WORKER_COUNT_ENVIRONMENT_VARIABLE)):
        parser.error(
            f"${WORKER_COUNT_ENVIRONMENT_VARIABLE} names no process count; set it to a whole number of at least 1"
        )
    return arguments


def names_a_process_count(raw_value: str | None) -> bool:
    """Whether the variable uvicorn reads a process count from is unset, or holds a count it can start."""
    if raw_value is None:
        return True
    try:
        return positive_integer(raw_value) >= 1
    except argparse.ArgumentTypeError:
        return False
