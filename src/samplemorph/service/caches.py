from __future__ import annotations

from collections import OrderedDict


class LruCache[Key, Value]:
    """A bounded map that forgets what was used longest ago once its capacity is reached.

    Reading a key counts as using it, so a value asked for again and again stays while the ones
    nobody returns to make room.
    """

    def __init__(self, *, capacity: int) -> None:
        self._capacity = capacity
        self._entries: OrderedDict[Key, Value] = OrderedDict()

    def get(self, key: Key) -> Value | None:
        """The value stored under `key`, refreshed as the most recently used, or None when absent."""
        value = self._entries.get(key)
        if value is not None:
            self._entries.move_to_end(key)
        return value

    def put(self, key: Key, value: Value) -> None:
        """Store `value` under `key` as the most recently used, dropping the least recent past capacity."""
        self._entries[key] = value
        self._entries.move_to_end(key)
        while len(self._entries) > self._capacity:
            self._entries.popitem(last=False)

    def __len__(self) -> int:
        return len(self._entries)
