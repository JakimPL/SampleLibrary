from __future__ import annotations

import sys
from typing import Protocol

from samplelibrary.environment import PACKAGE_NAME


class ProgramResolver(Protocol):
    """What runs a step's command, given the command a step names."""

    def program(self, step: str, command: tuple[str, ...]) -> list[str]:
        """The executable and its own arguments, which the step's command line follows."""


class SampleLibraryPrograms:  # pylint: disable=unused-argument
    """Every step runs as this project's own command line, in a process of its own."""

    def program(self, step: str, command: tuple[str, ...]) -> list[str]:
        return [sys.executable, "-m", PACKAGE_NAME]
