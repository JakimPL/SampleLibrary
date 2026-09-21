from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from queue import Queue
from typing import Any, Protocol

from tqdm import tqdm


class ProgressSink(Protocol):
    """Where a pass reports the work it has finished, leaving the caller to decide how it shows.

    One pass covers its work the same way whether it runs alone or as one of several workers; what
    differs is where the count goes -- a bar on this terminal, or a queue back to the process that
    owns one.
    """

    def advance(self, count: int) -> None:
        """Record ``count`` further work items as finished."""


@dataclass(frozen=True)
class BarProgress:
    """A ProgressSink drawing the count onto a tqdm bar."""

    progress_bar: Any  # tqdm ships no annotations of its own, so its type arrives untyped.

    def advance(self, count: int) -> None:
        self.progress_bar.update(count)


@contextmanager
def progress_bar(total: int, *, description: str) -> Iterator[BarProgress]:
    """One bar covering a whole pass, closed once the pass ends."""
    with tqdm(total=total, desc=description) as tqdm_bar:
        yield BarProgress(tqdm_bar)


@dataclass(frozen=True)
class QueueProgress:
    """A ProgressSink handing its count to whichever process owns the bar."""

    counts: Queue[int]

    def advance(self, count: int) -> None:
        self.counts.put(count)
