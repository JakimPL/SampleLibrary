from __future__ import annotations

import multiprocessing
from collections.abc import Callable, Iterator, Sequence
from typing import TypeVar

from threadpoolctl import threadpool_limits
from tqdm import tqdm

from sampledescriptor.training import WORKER_START_METHOD

Item = TypeVar("Item")
Result = TypeVar("Result")


def limit_process_threads() -> None:
    """One thread per worker process, so a dozen of them share the cores rather than contend for all of them."""
    threadpool_limits(limits=1)


def mapped_in_processes(
    work: Callable[[Item], Result],
    items: Sequence[Item],
    *,
    worker_count: int,
    chunk_size: int,
    description: str,
) -> Iterator[Result]:
    """Each item's result in order, from a pool of fresh processes or, with none asked for, in this one.

    `work` is sent to every process once, so it carries whatever each item needs; every process is
    held to one thread. Progress is drawn under `description`, one step per item.
    """
    progress = tqdm(total=len(items), desc=description, unit="item")
    if worker_count == 0:
        for item in items:
            yield work(item)
            progress.update()
    else:
        with multiprocessing.get_context(WORKER_START_METHOD).Pool(
            worker_count, initializer=limit_process_threads
        ) as pool:
            for result in pool.imap(work, items, chunksize=chunk_size):
                yield result
                progress.update()
    progress.close()
