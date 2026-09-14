from __future__ import annotations

from samplemorph.service.caches import LruCache


def _cache(capacity: int) -> LruCache[str, bytes]:
    return LruCache(capacity=capacity, weigh=len)


def test_the_least_recently_used_entries_make_room_until_the_bytes_fit() -> None:
    cache = _cache(10)
    cache.put("first", b"1234")
    cache.put("second", b"1234")

    cache.put("third", b"123456")

    assert cache.get("first") is None
    assert cache.get("second") == b"1234"
    assert cache.get("third") == b"123456"
    assert cache.weight == 10


def test_reading_an_entry_keeps_it_from_being_the_one_dropped() -> None:
    cache = _cache(8)
    cache.put("first", b"1234")
    cache.put("second", b"1234")

    assert cache.get("first") == b"1234"
    cache.put("third", b"1234")

    assert cache.get("second") is None
    assert cache.get("first") == b"1234"


def test_storing_a_key_again_replaces_its_value_and_its_weight() -> None:
    cache = _cache(8)
    cache.put("first", b"1234")

    cache.put("first", b"12")

    assert cache.get("first") == b"12"
    assert (len(cache), cache.weight) == (1, 2)


def test_a_value_heavier_than_the_whole_cache_is_not_kept() -> None:
    cache = _cache(8)
    cache.put("kept", b"1234")

    cache.put("oversized", b"123456789")

    assert cache.get("oversized") is None
    assert cache.get("kept") == b"1234"
