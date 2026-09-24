from __future__ import annotations

import logging
import multiprocessing
import os
from collections.abc import Callable, Iterable
from concurrent.futures import Future, ProcessPoolExecutor, wait
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Final, Generic, TypeVar

from samplecore.cli_support import open_catalog_connection
from samplecore.config import LibraryConfig
from samplecore.models.scalars import MINIMUM_WORKER_COUNT, WorkerCount
from sampleextract.parallel.division import divide
from sampleextract.parallel.worker import ShareCover, cover_share
from sampleextract.progress import ProgressSink, progress_bar

MAXIMUM_AUTOMATIC_WORKERS: Final[int] = 8
_START_METHOD: Final[str] = "spawn"
_DRAW_INTERVAL_SECONDS: Final[float] = 0.1

Item = TypeVar("Item")
Summary = TypeVar("Summary")

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkList(Generic[Item]):
    """What a pass covers, and how its bar and its log name the work."""

    items: tuple[Item, ...]
    description: str
    noun: str


@dataclass(frozen=True)
class SharesOutcome(Generic[Summary]):
    """What the shares of one pass reported between them, and the error each share that stopped raised."""

    summary: Summary
    worker_errors: tuple[BaseException, ...]


def default_worker_count() -> WorkerCount:
    """How many processes a run spends when it is left to choose for itself.

    One per core is what parsing, being ordinary Python, can actually use. The ceiling is what the
    machine's memory bounds: one module can materialize tens of thousands of note events, and each
    worker carries that alone. A run told a number of its own takes that number instead.
    """
    return min(os.cpu_count() or MINIMUM_WORKER_COUNT, MAXIMUM_AUTOMATIC_WORKERS)


def cover_in_shares(
    config: LibraryConfig,
    work: WorkList[Item],
    *,
    workers: WorkerCount,
    cover: ShareCover[Item, Summary],
    combine: Callable[[Iterable[Summary]], Summary],
) -> SharesOutcome[Summary]:
    """Cover a work list once, spending ``workers`` processes on it.

    The list is gathered by the caller, in one place, and the shares handed out from it, so every
    worker covers a share of the same list and the catalog sees each item reached by one of them.
    ``cover`` is the pass one share runs, a module-level function so a spawned process can import it,
    and ``combine`` reads the shares' summaries as the one pass they made up between them.
    """
    shares = tuple(share for share in divide(work.items, workers=workers) if share)
    if len(shares) <= 1:
        with progress_bar(len(work.items), description=work.description) as progress:
            return SharesOutcome(summary=_cover_here(config, work.items, cover, progress=progress), worker_errors=())

    _logger.info("Spending %d worker processes on %d %s.", len(shares), len(work.items), work.noun)
    with progress_bar(len(work.items), description=work.description) as progress:
        return _cover_across_processes(config, shares, cover=cover, combine=combine, progress=progress)


def _cover_here(
    config: LibraryConfig, items: tuple[Item, ...], cover: ShareCover[Item, Summary], *, progress: ProgressSink
) -> Summary:
    """Cover the work list in this process, which is what a single share amounts to."""
    with open_catalog_connection(config.catalog_url()) as connection:
        return cover(config, connection, items, progress=progress)


def _cover_across_processes(
    config: LibraryConfig,
    shares: tuple[tuple[Item, ...], ...],
    *,
    cover: ShareCover[Item, Summary],
    combine: Callable[[Iterable[Summary]], Summary],
    progress: ProgressSink,
) -> SharesOutcome[Summary]:
    """Spend one process per share, drawing what they all report onto this process's own bar.

    Processes rather than threads, since parsing is where the time goes and it is ordinary Python.
    Spawn rather than whichever start method the platform defaults to: this process holds no
    catalog connection while the children start, and naming spawn keeps that true wherever the run
    happens, at the cost of about a second of startup against a pass measured in hours.

    A share that stops leaves its error on the future it was given. The other shares carry on to
    their end, since every item they land is kept by a rerun anyway, and what they report is
    combined beside the errors of the shares that stopped, so a caller reports both.
    """
    context = multiprocessing.get_context(_START_METHOD)
    with context.Manager() as manager, ProcessPoolExecutor(max_workers=len(shares), mp_context=context) as pool:
        counts: Queue[int] = manager.Queue()
        futures = [pool.submit(cover_share, config, share, counts, cover) for share in shares]
        _draw_until_finished(futures, counts=counts, progress=progress)
        errors = tuple(error for error in (future.exception() for future in futures) if error is not None)
        finished = combine(future.result() for future in futures if future.exception() is None)
        return SharesOutcome(summary=finished, worker_errors=errors)


def _draw_until_finished(futures: list[Future[Summary]], *, counts: Queue[int], progress: ProgressSink) -> None:
    """Move what the workers report onto the bar for as long as any of them is still working."""
    pending = set(futures)
    while pending:
        pending = wait(pending, timeout=_DRAW_INTERVAL_SECONDS).not_done
        _draw_what_arrived(counts, progress=progress)


def _draw_what_arrived(counts: Queue[int], *, progress: ProgressSink) -> None:
    """Take everything waiting on the queue at this moment onto the bar."""
    while True:
        try:
            count = counts.get_nowait()
        except Empty:
            return

        progress.advance(count)
