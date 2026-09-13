from __future__ import annotations

import logging
import multiprocessing
import os
from concurrent.futures import Future, ProcessPoolExecutor, wait
from pathlib import Path
from queue import Empty, Queue
from typing import Final

from samplecore.cli_support import open_catalog_connection
from samplecore.config import LibraryConfig
from samplecore.models.scalars import MINIMUM_WORKER_COUNT, WorkerCount
from sampleextract.discovery import discover_modules
from sampleextract.parallel.division import divide
from sampleextract.parallel.worker import extract_share
from sampleextract.progress import ProgressSink, extraction_bar
from sampleextract.run import ExtractionSummary, run_extraction

MAXIMUM_AUTOMATIC_WORKERS: Final[int] = 8
_START_METHOD: Final[str] = "spawn"
_DRAW_INTERVAL_SECONDS: Final[float] = 0.1

_logger = logging.getLogger(__name__)


def default_worker_count() -> WorkerCount:
    """How many processes a run spends when it is left to choose for itself.

    One per core is what parsing, being ordinary Python, can actually use. The ceiling is what the
    machine's memory bounds: one module can materialize tens of thousands of note events, and each
    worker carries that alone. A run told a number of its own takes that number instead.
    """
    return min(os.cpu_count() or MINIMUM_WORKER_COUNT, MAXIMUM_AUTOMATIC_WORKERS)


def extract_corpus(config: LibraryConfig, *, workers: WorkerCount) -> ExtractionSummary:
    """Cover the configured source directory once, spending ``workers`` processes on it.

    The corpus is walked here, in one place, and the shares handed out from it, so every worker
    covers a share of the same list and the catalog sees each module reached by one of them.
    """
    paths = discover_modules(config.module_source_directory)
    shares = tuple(share for share in divide(paths, workers=workers) if share)
    if len(shares) <= 1:
        with extraction_bar(len(paths)) as progress:
            return _extract_here(config, paths, progress=progress)

    _logger.info("Spending %d worker processes on %d modules.", len(shares), len(paths))
    with extraction_bar(len(paths)) as progress:
        return _extract_across_processes(config, shares, progress=progress)


def _extract_here(config: LibraryConfig, paths: tuple[Path, ...], *, progress: ProgressSink) -> ExtractionSummary:
    """Cover the corpus in this process, which is what a single share amounts to."""
    with open_catalog_connection(config.database_url) as connection:
        return run_extraction(config, connection, paths, progress=progress)


def _extract_across_processes(
    config: LibraryConfig, shares: tuple[tuple[Path, ...], ...], *, progress: ProgressSink
) -> ExtractionSummary:
    """Spend one process per share, drawing what they all report onto this process's own bar.

    Processes rather than threads, since parsing is where the time goes and it is ordinary Python.
    Spawn rather than whichever start method the platform defaults to: this process holds no
    catalog connection while the children start, and naming spawn keeps that true wherever the run
    happens, at the cost of about a second of startup against a pass measured in hours.

    A worker that dies leaves its failure on the future it was given, which surfaces here as the
    run's own: work this size is worth stopping for rather than finishing quietly short.
    """
    context = multiprocessing.get_context(_START_METHOD)
    with context.Manager() as manager, ProcessPoolExecutor(max_workers=len(shares), mp_context=context) as pool:
        counts: Queue[int] = manager.Queue()
        futures = [pool.submit(extract_share, config, share, counts) for share in shares]
        _draw_until_finished(futures, counts=counts, progress=progress)
        return ExtractionSummary.combine(future.result() for future in futures)


def _draw_until_finished(
    futures: list[Future[ExtractionSummary]], *, counts: Queue[int], progress: ProgressSink
) -> None:
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
