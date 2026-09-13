from __future__ import annotations

import argparse
import signal
import subprocess
import sys
from types import FrameType
from typing import Final

from samplecore.cli_support import bootstrap_cli, port_number
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
    sys.exit(run_interface(interface_command(tracking_uri(config.library_root), port=arguments.port)))


def run_interface(command: list[str]) -> int:
    """Run the interface as a child process until it stops, reporting its exit status.

    MLflow's server starts worker processes of its own and stops them when it is asked to stop, so a
    termination request sent to this command is handed on to MLflow, and nothing it started outlives
    the command. An interrupt from the terminal reaches the whole foreground process group, MLflow
    included, so this process waits for MLflow to finish stopping.
    """
    child = subprocess.Popen(command)

    def hand_on_termination(signal_number: int, _frame: FrameType | None) -> None:
        child.send_signal(signal_number)

    previous_termination = signal.signal(signal.SIGTERM, hand_on_termination)
    previous_interrupt = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        return child.wait()
    finally:
        signal.signal(signal.SIGTERM, previous_termination)
        signal.signal(signal.SIGINT, previous_interrupt)


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
    parser.add_argument("--port", type=port_number, default=DEFAULT_PORT, help="The port the interface listens on.")
    return parser.parse_args(argv)
