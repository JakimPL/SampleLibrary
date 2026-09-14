from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable


class LruCache[Key, Value]:
    """A map bounded by the weight of what it holds, forgetting what was used longest ago to stay within it.

    Reading a key counts as using it, so a value asked for again and again stays while the ones
    nobody returns to make room. A value heavier than the whole capacity is not kept at all.
    """

    def __init__(self, *, capacity: int, weigh: Callable[[Value], int]) -> None:
        self._capacity = capacity
        self._weigh = weigh
        self._entries: OrderedDict[Key, tuple[Value, int]] = OrderedDict()
        self._weight = 0

    @property
    def weight(self) -> int:
        return self._weight

    def get(self, key: Key) -> Value | None:
        """The value stored under `key`, refreshed as the most recently used, or None when absent."""
        entry = self._entries.get(key)
        if entry is None:
            return None
        self._entries.move_to_end(key)
        return entry[0]

    def put(self, key: Key, value: Value) -> None:
        """Store `value` under `key` as the most recently used, dropping the least recent until the weight fits."""
        weight = self._weigh(value)
        if weight > self._capacity:
            return
        previous = self._entries.pop(key, None)
        if previous is not None:
            self._weight -= previous[1]
        self._entries[key] = (value, weight)
        self._weight += weight
        while self._weight > self._capacity:
            _, (_, dropped) = self._entries.popitem(last=False)
            self._weight -= dropped

    def __len__(self) -> int:
        return len(self._entries)
