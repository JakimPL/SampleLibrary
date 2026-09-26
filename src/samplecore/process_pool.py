from __future__ import annotations

import multiprocessing
import os
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Final

from threadpoolctl import threadpool_limits

from samplecore.progress import ProgressBar

# Every worker process a pass starts is a fresh interpreter, which keeps a worker's memory its own
# rather than a copy of a process holding a catalog connection or the GPU.
WORKER_START_METHOD: Final[str] = "spawn"
IN_PROCESS_WORKERS: Final[int] = 0
SINGLE_THREAD: Final[int] = 1
# Each numerical library sizes its thread pool from its variable as it first loads.
SINGLE_THREAD_ENVIRONMENT: Final[Mapping[str, str]] = {
    "OPENBLAS_NUM_THREADS": str(SINGLE_THREAD),
    "OMP_NUM_THREADS": str(SINGLE_THREAD),
    "MKL_NUM_THREADS": str(SINGLE_THREAD),
    "VECLIB_MAXIMUM_THREADS": str(SINGLE_THREAD),
    "NUMBA_NUM_THREADS": str(SINGLE_THREAD),
}


@dataclass
class _InstalledWork:
    """The work a worker process received as it started, which every item it is handed runs through."""

    work: Callable[[Any], Any] | None = None


_INSTALLED: Final[_InstalledWork] = _InstalledWork()


def limit_process_threads() -> None:
    """One thread per worker process, so a dozen of them share the cores rather than contend for all of them."""
    threadpool_limits(limits=SINGLE_THREAD)


@contextmanager
def single_threaded_children() -> Iterator[None]:
    """Start processes under an environment that holds every numerical library in them to one thread.

    A library sizes its thread pool as it first loads, and a worker loads most of its libraries
    after it starts -- scipy's own linear algebra, for one, loads with the first function that
    needs it. The environment a process starts under is the one setting every such library reads,
    so a worker computes on one thread whichever library it loads, and whenever. The variables are
    restored once the processes have started, so this process keeps the pools it sized itself.
    """
    previous = {name: os.environ.get(name) for name in SINGLE_THREAD_ENVIRONMENT}
    os.environ.update(SINGLE_THREAD_ENVIRONMENT)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def mapped_in_processes[Item, Result](
    work: Callable[[Item], Result],
    items: Sequence[Item],
    *,
    worker_count: int,
    chunk_size: int,
    description: str,
) -> Iterator[Result]:
    """Each item's result in order, from a pool of fresh processes or, with `IN_PROCESS_WORKERS` asked for, in this one.

    `work` is sent to every process once, as it starts, so it carries whatever each item needs and
    only the items travel after that; every process computes on one thread. Progress is drawn under
    `description`, one step per item.
    """
    with ProgressBar(total=len(items), label=description) as progress:
        if worker_count == IN_PROCESS_WORKERS:
            for item in items:
                yield work(item)
                progress.update(1)
        else:
            with single_threaded_children():
                pool = multiprocessing.get_context(WORKER_START_METHOD).Pool(
                    worker_count, initializer=_start_worker, initargs=(work,)
                )
            with pool:
                for result in pool.imap(_apply, items, chunksize=chunk_size):
                    yield result
                    progress.update(1)


def _start_worker(work: Callable[[Any], Any]) -> None:
    limit_process_threads()
    _INSTALLED.work = work


def _apply(item: Any) -> Any:
    work = _INSTALLED.work
    if work is None:
        raise RuntimeError("a worker was handed an item before it received its work")
    return work(item)
