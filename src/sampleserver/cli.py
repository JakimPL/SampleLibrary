from __future__ import annotations

import argparse
from typing import Final

import uvicorn

APPLICATION_PATH: Final[str] = "sampleserver.main:app"
DEFAULT_HOST: Final[str] = "127.0.0.1"
DEFAULT_PORT: Final[int] = 8000
DEFAULT_WORKERS: Final[int] = 1


def main(argv: list[str], *, prog: str) -> None:
    """Serve the API over HTTP.

    uvicorn imports the app by its path in every process it starts, so each worker, and each
    restart under `--reload`, reads the configuration afresh.
    """
    arguments = _parse_arguments(argv, prog=prog)
    uvicorn.run(
        APPLICATION_PATH,
        host=arguments.host,
        port=arguments.port,
        reload=arguments.reload,
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
        "--workers", type=int, default=DEFAULT_WORKERS, help="How many processes serve requests side by side."
    )
    return parser.parse_args(argv)
