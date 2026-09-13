from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from samplecore.models.scalars import WorkerCount


def divide(paths: Sequence[Path], *, workers: WorkerCount) -> tuple[tuple[Path, ...], ...]:
    """Split a work list into one share per worker, each taking every ``workers``-th path.

    Striding rather than slicing into blocks keeps the shares alike: a work list ordered by path
    puts a directory's worth of similar files together, so contiguous blocks would hand one worker
    all the large ones. Between them the shares cover the list exactly once, which is what lets
    every worker write to one catalog and still leave each module to a single one of them.

    A division finer than the work list leaves the later shares empty, so a corpus smaller than the
    worker count still comes out covered once.
    """
    return tuple(tuple(paths[offset::workers]) for offset in range(workers))
