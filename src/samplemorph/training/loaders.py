from __future__ import annotations

from collections.abc import Callable
from typing import Final, TypedDict, TypeVar

import torch
from threadpoolctl import threadpool_limits
from torch.utils.data import DataLoader, Dataset, Sampler

from samplemorph.training import WORKER_START_METHOD
from samplemorph.training.refusals import TrainingDataShortfall

PREFETCH_BATCHES: Final[int] = 2

Item = TypeVar("Item")
Request = TypeVar("Request")


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


def require_full_batch(sample_count: int, *, batch_size: int, flags: str) -> None:
    """Make sure a training set fills at least one whole batch, since training batches drop a short tail.

    `flags` names the command-line flags that shrink a batch, for the message.

    Raises:
        TrainingDataShortfall: the training set holds fewer samples than one batch.
    """
    if sample_count == 0:
        raise TrainingDataShortfall("no training sample is left once the validation samples are set aside")
    if sample_count < batch_size:
        raise TrainingDataShortfall(
            f"{sample_count} training samples fill no batch of {batch_size}; set {flags} so a batch takes "
            f"{sample_count} or fewer"
        )


def build_loader(
    dataset: Dataset[Item],
    *,
    batch_size: int,
    worker_count: int,
    sampler: Sampler[Request] | None,
    drop_last: bool,
) -> DataLoader[Item]:
    """A loader on the transport a long run survives, shared by every trainer here.

    Each worker starts as a fresh interpreter, so it holds its own imports and working arrays and
    nothing else -- a worker started fresh begins with an address space of its own rather than a
    copy of the trainer's, which is what a page-table copy of a process holding the GPU asks the
    kernel to do. Batches travel as ordinary pageable memory, each worker holds `PREFETCH_BATCHES`
    ready, and each worker computes on one thread, so a dozen of them share the cores rather than
    contend for all of them. The `sampler` decides the order items are read in, the dataset's own
    order when left out.
    """
    return DataLoader(
        dataset,
        batch_size=batch_size,
        sampler=sampler,
        drop_last=drop_last,
        **_worker_options(worker_count),
    )


def build_batched_loader(
    dataset: Dataset[Item], *, worker_count: int, batch_sampler: Sampler[list[Request]]
) -> DataLoader[Item]:
    """A loader like `build_loader` whose batches the `batch_sampler` names whole, requests and all."""
    return DataLoader(dataset, batch_sampler=batch_sampler, **_worker_options(worker_count))


def _worker_options(worker_count: int) -> WorkerOptions:
    parallel = worker_count > 0
    return WorkerOptions(
        num_workers=worker_count,
        persistent_workers=parallel,
        worker_init_fn=limit_worker_threads if parallel else None,
        prefetch_factor=PREFETCH_BATCHES if parallel else None,
        multiprocessing_context=WORKER_START_METHOD if parallel else None,
    )


class WorkerOptions(TypedDict):
    num_workers: int
    persistent_workers: bool
    worker_init_fn: Callable[[int], None] | None
    prefetch_factor: int | None
    multiprocessing_context: str | None
