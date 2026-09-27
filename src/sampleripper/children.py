from __future__ import annotations

import logging
import subprocess
import sys
from collections.abc import Mapping
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import IO, Final

from sampleripper.environment import PACKAGE_NAME

STOP_WAIT_SECONDS: Final[float] = 10.0

_logger = logging.getLogger(__name__)


def sampleripper_command(*arguments: str) -> tuple[str, ...]:
    """A command line running this project's own command in the interpreter the application runs in."""
    return (sys.executable, "-m", PACKAGE_NAME, *arguments)


class ChildProcess:
    """A program a process starts beside itself, in the environment it is handed, writing to a log or to the starter's output.

    ``log_path`` names the file the program's output is appended to; ``None`` leaves the output to go
    where the starting process's own goes, which is how a site's platform reads both. The starter
    stops it on its way out: a termination first, then a kill once the program has had
    `STOP_WAIT_SECONDS` to end.
    """

    def __init__(
        self, name: str, command: tuple[str, ...], *, environment: Mapping[str, str], log_path: Path | None
    ) -> None:
        self.name = name
        self._command = command
        self._environment = dict(environment)
        self._log_path = log_path
        self._process: subprocess.Popen[bytes] | None = None

    @property
    def environment(self) -> Mapping[str, str]:
        """The environment the program starts in."""
        return self._environment

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        """Start the program, its output appended to its log or joining the starter's own."""
        if self._log_path is not None:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            _logger.info("Starting the %s; its log is %s.", self.name, self._log_path)
        else:
            _logger.info("Starting the %s.", self.name)
        with self._output() as output:
            self._process = subprocess.Popen(  # pylint: disable=consider-using-with
                self._command,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT if output is not None else None,
                env=self._environment,
            )

    def wait(self) -> int:
        """Wait for the program to end, and return its exit status.

        Raises:
            RuntimeError: the program was never started.
        """
        if self._process is None:
            raise RuntimeError(f"the {self.name} was never started")
        return self._process.wait()

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

    def _output(self) -> AbstractContextManager[IO[bytes] | None]:
        return self._log_path.open("ab") if self._log_path is not None else nullcontext(None)
