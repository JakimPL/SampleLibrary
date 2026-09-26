from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from samplecore.processes import HIDDEN_CONSOLE_FLAGS
from samplelibrary.environment import PACKAGE_NAME
from samplelibrary.pipeline.devices import BuildDevice

STOP_WAIT_SECONDS: Final[float] = 10.0
DEVICE_PROBE_SECONDS: Final[float] = 120.0

_logger = logging.getLogger(__name__)


def samplelibrary_command(*arguments: str) -> tuple[str, ...]:
    """A command line running this project's own command in the interpreter the application runs in."""
    return (sys.executable, "-m", PACKAGE_NAME, *arguments)


class ChildProcess:
    """A program the application starts beside itself, reading the application's config file and writing a log.

    The application stops it on its way out: a termination first, then a kill once the program has
    had `STOP_WAIT_SECONDS` to end.
    """

    def __init__(self, name: str, command: tuple[str, ...], *, config_path: Path, log_path: Path) -> None:
        self.name = name
        self._command = command
        self._config_path = config_path
        self._log_path = log_path
        self._process: subprocess.Popen[bytes] | None = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        """Start the program, its output appended to its log."""
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        _logger.info("Starting the %s; its log is %s.", self.name, self._log_path)
        with self._log_path.open("ab") as log:
            self._process = subprocess.Popen(  # pylint: disable=consider-using-with
                self._command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=child_environment(self._config_path),
            )

    def stop(self) -> None:
        if self._process is None or self._process.poll() is not None:
            return
        _logger.info("Stopping the %s.", self.name)
        self._process.terminate()
        try:
            self._process.wait(timeout=STOP_WAIT_SECONDS)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()


def probe_build_device(command: tuple[str, ...], *, config_path: Path) -> BuildDevice:
    """The device builds compute on, as ``command`` names it, or the processor where the command fails to say.

    The command imports torch, which the application's own process leaves out, so it runs apart.
    """
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=True,
            timeout=DEVICE_PROBE_SECONDS,
            env=child_environment(config_path),
            creationflags=HIDDEN_CONSOLE_FLAGS,
        )
        return BuildDevice.model_validate_json(completed.stdout)
    except (OSError, subprocess.SubprocessError, ValidationError) as error:
        _logger.warning("Could not tell which device builds use, so they count on the processor: %s", error)
        return BuildDevice(card=None)


def child_environment(config_path: Path) -> dict[str, str]:
    """The environment of a program the application starts: its own, pointing at the application's config file."""
    return {**os.environ, CONFIG_PATH_ENVIRONMENT_VARIABLE: str(config_path)}
