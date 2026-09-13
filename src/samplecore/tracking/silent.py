from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

SILENT_RUN_ID: Final[str] = "untracked"


@dataclass(frozen=True)
class SilentRun:
    """A run that keeps nothing, for the passes whose numbers are read once and thrown away.

    Every pipeline reports through the same calls whether or not anyone is recording, so a quick
    experiment and a kept one run the same code. Its identity is a fixed stand-in, which reads
    plainly in a log line as the reason no record exists to look up.
    """

    @property
    def run_id(self) -> str:
        return SILENT_RUN_ID

    def log_parameters(self, parameters: dict[str, str]) -> None:
        """Accept what this run was asked to do, keeping none of it."""

    def log_metrics(self, metrics: dict[str, float], *, step: int) -> None:
        """Accept what this run measured, keeping none of it."""

    def log_artifact(self, path: Path) -> None:
        """Accept a file this run produced, leaving it where it was written."""
