from __future__ import annotations

from typing import Final, TypeVar

import torch
from threadpoolctl import threadpool_limits
from torch.utils.data import DataLoader, Dataset, Sampler

from samplemorph.training import WORKER_START_METHOD

PREFETCH_BATCHES: Final[int] = 2

Item = TypeVar("Item")


def limit_worker_threads(_worker_id: int) -> None:
    """Hold each loader process to one compute thread.

    A loader calls this in each worker it starts, handing it that worker's index, which this has no
    use for. Every worker derives its examples through the same linear algebra, and each library
    underneath would otherwise spread one worker's work across every core the machine has. A dozen
    workers doing that at once spend most of their time contending rather than computing: measured
    here, one example costs 96 ms with one thread and the pool as a whole managed 31 examples a
    second across twelve workers, where one thread each reaches four times that.
    """
    threadpool_limits(limits=1)
    torch.set_num_threads(1)


def build_loader(
    dataset: Dataset[Item],
    *,
    batch_size: int,
    worker_count: int,
    shuffle: bool,
    batch_sampler: Sampler[list[int]] | None = None,
) -> DataLoader[Item]:
    """A loader on the transport a long run survives, shared by every trainer here.

    Each worker starts as a fresh interpreter, so it holds its own imports and working arrays and
    nothing else -- a worker started fresh begins with an address space of its own rather than a
    copy of the trainer's, which is what a page-table copy of a process holding the GPU asks the
    kernel to do. Batches travel as ordinary pageable memory, each worker holds `PREFETCH_BATCHES`
    ready, and each worker computes on one thread, so a dozen of them share the cores rather than
    contend for all of them. A `batch_sampler` names whole batches itself, in which case the
    loader neither sizes nor shuffles them.
    """
    parallel = worker_count > 0
    return DataLoader(
        dataset,
        batch_size=batch_size if batch_sampler is None else 1,
        shuffle=shuffle if batch_sampler is None else False,
        batch_sampler=batch_sampler,
        num_workers=worker_count,
        drop_last=shuffle if batch_sampler is None else False,
        persistent_workers=parallel,
        worker_init_fn=limit_worker_threads if parallel else None,
        prefetch_factor=PREFETCH_BATCHES if parallel else None,
        multiprocessing_context=WORKER_START_METHOD if parallel else None,
    )
