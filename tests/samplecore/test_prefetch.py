from __future__ import annotations

import threading
from typing import Final

import pytest

from samplecore.prefetch import prefetched

DEPTH: Final[int] = 3


class UnreadableItem(Exception):
    """Raised by the work standing in for a read that fails."""


def test_every_item_arrives_in_order_with_its_result() -> None:
    assert list(prefetched(range(10), lambda item: item * item, depth=DEPTH)) == [
        (item, item * item) for item in range(10)
    ]


def test_the_work_runs_no_further_ahead_than_its_depth() -> None:
    started: list[int] = []
    released = threading.Event()

    def work(item: int) -> int:
        started.append(item)
        if item >= DEPTH:
            released.wait()
        return item

    results = prefetched(range(10), work, depth=DEPTH)
    assert next(results) == (0, 0)
    assert max(started) <= DEPTH
    released.set()
    results.close()


def test_a_failure_reaches_the_consumer_at_its_own_item() -> None:
    def work(item: int) -> int:
        if item == 2:
            raise UnreadableItem("the third item cannot be read")
        return item

    results = prefetched(range(5), work, depth=DEPTH)

    assert [next(results), next(results)] == [(0, 0), (1, 1)]
    with pytest.raises(UnreadableItem, match="third item"):
        next(results)
