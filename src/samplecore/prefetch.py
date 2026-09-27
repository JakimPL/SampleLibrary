from __future__ import annotations

from collections import deque
from collections.abc import Callable, Generator, Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from itertools import islice


def prefetched[Item, Result](
    items: Iterable[Item], work: Callable[[Item], Result], *, depth: int
) -> Generator[tuple[Item, Result]]:
    """Each item with the result of ``work`` on it, in order, the results computed ahead in a thread of their own.

    The thread runs at most ``depth`` items ahead of the consumer, so reading the next items overlaps
    whatever the consumer does with the current one. An exception ``work`` raises reaches the
    consumer at the item it was raised for, and work queued beyond a consumer that stops is dropped.
    """
    remaining = iter(items)
    executor = ThreadPoolExecutor(max_workers=1)
    queued: deque[tuple[Item, Future[Result]]] = deque(
        (item, executor.submit(work, item)) for item in islice(remaining, depth)
    )
    try:
        while queued:
            item, future = queued.popleft()
            result = future.result()
            for following in islice(remaining, 1):
                queued.append((following, executor.submit(work, following)))
            yield item, result
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
