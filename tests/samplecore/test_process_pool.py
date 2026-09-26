from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Final

import pytest
from threadpoolctl import threadpool_info

from samplecore.process_pool import SINGLE_THREAD, SINGLE_THREAD_ENVIRONMENT, mapped_in_processes

WORKER_COUNT: Final[int] = 2
ITEM_COUNT: Final[int] = 12


@dataclass(frozen=True)
class ThreadsAfterLoading:
    """Loads scipy's linear algebra only once it runs, as a worker's own libraries load after it starts."""

    def __call__(self, item: int) -> int:
        # pylint: disable-next=import-outside-toplevel,unused-import
        import scipy.linalg  # noqa: F401

        return max(library["num_threads"] for library in threadpool_info())


@dataclass(frozen=True)
class WorkIdentity:
    def __call__(self, item: int) -> tuple[int, int]:
        return os.getpid(), id(self)


def test_a_worker_computes_on_one_thread_in_every_library_it_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in SINGLE_THREAD_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)

    threads = mapped_in_processes(
        ThreadsAfterLoading(), range(ITEM_COUNT), worker_count=WORKER_COUNT, chunk_size=1, description="Loading"
    )

    assert set(threads) == {SINGLE_THREAD}
    assert all(name not in os.environ for name in SINGLE_THREAD_ENVIRONMENT)


def test_a_worker_receives_its_work_once() -> None:
    identities = mapped_in_processes(
        WorkIdentity(), range(ITEM_COUNT), worker_count=WORKER_COUNT, chunk_size=1, description="Identifying"
    )

    works_by_process: defaultdict[int, set[int]] = defaultdict(set)
    for process, work in identities:
        works_by_process[process].add(work)
    assert all(len(works) == 1 for works in works_by_process.values())
