from __future__ import annotations

from pathlib import Path
from typing import Protocol


class TrackedRun(Protocol):
    """One recorded pass of a pipeline: what it was asked to do, and what it measured doing it.

    A run is opened by whichever command a person invoked, and handed to the machinery that has
    numbers to report. That direction is deliberate: a harness computes and returns, and the caller
    that already knows which run this is decides where the numbers go. It keeps every measurement
    reusable outside a tracked run, and keeps the tracker out of the code that does the work.

    Parameters describe the run before it starts and stay fixed; metrics describe what it found and
    may be recorded repeatedly against an advancing `step`.
    """

    @property
    def run_id(self) -> str:
        """The identity this run is recorded under, which its own record is reachable by."""

    def log_parameters(self, parameters: dict[str, str]) -> None:
        """Record what this run was asked to do."""

    def log_metrics(self, metrics: dict[str, float], *, step: int) -> None:
        """Record what this run measured, at a point in its progress."""

    def log_artifact(self, path: Path) -> None:
        """Record a file this run produced, stored alongside its numbers."""
