from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from samplecore.models.scalars import WorkerCount

Item = TypeVar("Item")


def divide(items: Sequence[Item], *, workers: WorkerCount) -> tuple[tuple[Item, ...], ...]:
    """Split a work list into one share per worker, each taking every ``workers``-th item.

    Striding rather than slicing into blocks keeps the shares alike: a work list ordered by path
    puts a directory's worth of similar files together, so contiguous blocks would hand one worker
    all the large ones. Between them the shares cover the list exactly once, which is what lets
    every worker write to one catalog and still leave each item to a single one of them.

    A division finer than the work list leaves the later shares empty, so a corpus smaller than the
    worker count still comes out covered once.
    """
    return tuple(tuple(items[offset::workers]) for offset in range(workers))
