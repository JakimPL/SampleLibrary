from __future__ import annotations

import argparse
from pathlib import Path
from typing import Final

import uvicorn

from samplecore.cli_support import bootstrap_cli, open_catalog_connection

APPLICATION_PATH: Final[str] = "sampleserver.main:app"
SOURCE_DIRECTORY: Final[Path] = Path(__file__).resolve().parents[1]
DEFAULT_HOST: Final[str] = "127.0.0.1"
DEFAULT_PORT: Final[int] = 8000


def main(argv: list[str], *, prog: str) -> None:
    """Serve the API over HTTP once its configuration loads and its catalog answers.

    uvicorn imports the app by its path in every process it starts, so each worker, and each
    restart under `--reload`, reads the configuration afresh. Checking both here first ends a
    broken start with one message and exit status 1, and prepares the catalog's schema once before
    any worker starts.
    """
    arguments = _parse_arguments(argv, prog=prog)
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
    parser = argparse.ArgumentParser(prog=prog, description="Serve the library's API over HTTP.")
    parser.add_argument("--host", type=str, default=DEFAULT_HOST, help="The address to bind.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="The port to bind.")
    processes = parser.add_mutually_exclusive_group()
    processes.add_argument(
        "--reload", action="store_true", help="Restart the server whenever a Python source file changes."
    )
    processes.add_argument(
        "--workers",
        type=int,
        default=None,
        help="How many processes serve requests side by side; $WEB_CONCURRENCY, or one, when left out.",
    )
    return parser.parse_args(argv)
