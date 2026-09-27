from __future__ import annotations

import multiprocessing
import os
import pickle
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass
from multiprocessing.pool import Pool
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import TracebackType
from typing import Any, Final, Protocol

from threadpoolctl import threadpool_limits

from samplecore.progress import ProgressBar

# Every worker process a pass starts is a fresh interpreter, which keeps a worker's memory its own
# rather than a copy of a process holding a catalog connection or the GPU.
WORKER_START_METHOD: Final[str] = "spawn"
IN_PROCESS_WORKERS: Final[int] = 0
STAGED_WORK_PREFIX: Final[str] = "sampleripper-work-"
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


class Mapper[Item, Result](Protocol):
    """Runs one piece of work over batches of items, each batch's results coming back in order."""

    def map(self, items: Sequence[Item], *, chunk_size: int) -> Iterator[Result]:
        """Each item's result in order; the items are handed out `chunk_size` at a time."""


@dataclass(frozen=True)
class _InProcessMapper[Item, Result]:
    work: Callable[[Item], Result]

    # pylint: disable-next=unused-argument
    def map(self, items: Sequence[Item], *, chunk_size: int) -> Iterator[Result]:
        return (self.work(item) for item in items)


@dataclass(frozen=True)
class _PoolMapper[Item, Result]:
    pool: Pool

    def map(self, items: Sequence[Item], *, chunk_size: int) -> Iterator[Result]:
        results: Iterator[Result] = self.pool.imap(_apply, items, chunksize=chunk_size)
        return results


class _WorkerPool[Item, Result]:
    """Fresh processes, each started under `single_threaded_children` with `work` installed, ended on leaving.

    `work` is pickled once into a private file every process reads as it starts. A process starting
    reads what it is handed only once it has imported what it needs, so work handed to each one
    directly would keep the next from starting until then; read from the file, the processes start
    together and load it side by side.
    """

    def __init__(self, work: Callable[[Item], Result], *, worker_count: int) -> None:
        self._work = work
        self._worker_count = worker_count
        self._pool: Pool | None = None
        self._staged: Path | None = None

    def __enter__(self) -> Mapper[Item, Result]:
        with NamedTemporaryFile(prefix=STAGED_WORK_PREFIX, delete=False) as file:
            pickle.dump(self._work, file, protocol=pickle.HIGHEST_PROTOCOL)
        self._staged = Path(file.name)
        with single_threaded_children():
            self._pool = multiprocessing.get_context(WORKER_START_METHOD).Pool(
                self._worker_count, initializer=_start_worker, initargs=(self._staged,)
            )
        return _PoolMapper(self._pool)

    def __exit__(
        self, error_type: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None
    ) -> None:
        if self._pool is not None:
            self._pool.terminate()
            self._pool.join()
        if self._staged is not None:
            self._staged.unlink(missing_ok=True)


def worker_pool[Item, Result](
    work: Callable[[Item], Result], *, worker_count: int
) -> AbstractContextManager[Mapper[Item, Result]]:
    """A pool of fresh processes running `work`, or, with `IN_PROCESS_WORKERS` asked for, this process running it.

    `work` is sent to every process once, as it starts, so it carries whatever each item needs and
    only the items travel after that; every process computes on one thread. A pass handing out work
    in several batches keeps one pool for all of them, and a batch handed out starts at once, so the
    caller prepares the next batch while the processes work through this one.
    """
    if worker_count == IN_PROCESS_WORKERS:
        return nullcontext(_InProcessMapper(work))
    return _WorkerPool(work, worker_count=worker_count)


def mapped_in_processes[Item, Result](
    work: Callable[[Item], Result],
    items: Sequence[Item],
    *,
    worker_count: int,
    chunk_size: int,
    progress: ProgressBar,
) -> Iterator[Result]:
    """Each item's result in order, from a `worker_pool` running `work`.

    Each result counts one step on the caller's `progress`, which knows the whole of the pass these
    items belong to.
    """
    with worker_pool(work, worker_count=worker_count) as mapper:
        for result in mapper.map(items, chunk_size=chunk_size):
            yield result
            progress.update(1)


def _start_worker(staged: Path) -> None:
    limit_process_threads()
    with staged.open("rb") as file:
        _INSTALLED.work = pickle.load(file)


def _apply(item: Any) -> Any:
    work = _INSTALLED.work
    if work is None:
        raise RuntimeError("a worker was handed an item before it received its work")
    return work(item)
