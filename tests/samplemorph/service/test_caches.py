from __future__ import annotations

from samplemorph.service.caches import LruCache


def test_the_least_recently_used_entry_makes_room_past_capacity() -> None:
    cache: LruCache[str, int] = LruCache(capacity=2)
    cache.put("first", 1)
    cache.put("second", 2)

    cache.put("third", 3)

    assert cache.get("first") is None
    assert cache.get("second") == 2
    assert cache.get("third") == 3
    assert len(cache) == 2


def test_reading_an_entry_keeps_it_from_being_the_one_dropped() -> None:
    cache: LruCache[str, int] = LruCache(capacity=2)
    cache.put("first", 1)
    cache.put("second", 2)

    assert cache.get("first") == 1
    cache.put("third", 3)

    assert cache.get("second") is None
    assert cache.get("first") == 1


def test_storing_a_key_again_replaces_its_value() -> None:
    cache: LruCache[str, int] = LruCache(capacity=2)
    cache.put("first", 1)

    cache.put("first", 10)

    assert cache.get("first") == 10
    assert len(cache) == 1
