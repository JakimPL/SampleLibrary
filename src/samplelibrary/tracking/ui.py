from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Final

from samplecore.cli_support import bootstrap_cli
from samplecore.tracking.store import tracking_uri

DEFAULT_PORT: Final[int] = 5000
LOCAL_HOST: Final[str] = "127.0.0.1"


def main(argv: list[str], *, prog: str) -> None:
    """Browse the configured library's recorded runs in MLflow's interface, served to this machine alone.

    Raises:
        SystemExit: with the interface's own exit status once it stops.
    """
    arguments = _parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    command = interface_command(tracking_uri(config.library_root), port=arguments.port)
    try:
        completed = subprocess.run(command, check=False)
    except KeyboardInterrupt:
        sys.exit(0)
    sys.exit(completed.returncode)


def interface_command(store_uri: str, *, port: int) -> list[str]:
    """The command line that serves MLflow's interface over one run store, through this interpreter."""
    return [
        sys.executable,
        "-m",
        "mlflow",
        "ui",
        "--backend-store-uri",
        store_uri,
        "--host",
        LOCAL_HOST,
        "--port",
        str(port),
    ]


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=prog, description="Browse the configured library's run store in MLflow's interface."
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="The port the interface listens on.")
    return parser.parse_args(argv)
