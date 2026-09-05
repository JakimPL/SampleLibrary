from __future__ import annotations

from datetime import UTC, datetime

import duckdb

from samplecore.models.module import Module
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.repositories.module import DuckDBModuleRepository


def _build_module(module_hash: str, module_id: int, *, tracker: TrackerFormat = TrackerFormat.XM) -> Module:
    return Module(
        hash=module_hash,
        id=module_id,
        filename="song.xm",
        tracker=tracker,
        title="a song",
        channel_count=8,
        pattern_count=32,
        instrument_count=16,
        sample_count=20,
        file_size=65536,
        ingested_at=datetime.now(UTC),
    )


def test_a_stored_module_round_trips_through_get(connection: duckdb.DuckDBPyConnection, module_hash_a: str) -> None:
    repository = DuckDBModuleRepository(connection)
    module = _build_module(module_hash_a, repository.next_id())

    repository.insert(module)

    assert repository.get(module_hash_a) == module


def test_get_on_an_unknown_hash_returns_none(connection: duckdb.DuckDBPyConnection, module_hash_a: str) -> None:
    repository = DuckDBModuleRepository(connection)

    assert repository.get(module_hash_a) is None


def test_next_id_produces_increasing_values(connection: duckdb.DuckDBPyConnection) -> None:
    repository = DuckDBModuleRepository(connection)

    first_id = repository.next_id()
    second_id = repository.next_id()

    assert second_id > first_id


def _insert_three_modules(repository: DuckDBModuleRepository) -> tuple[Module, Module, Module]:
    xm_module = _build_module(format(1, "064x"), repository.next_id(), tracker=TrackerFormat.XM)
    it_module = _build_module(format(2, "064x"), repository.next_id(), tracker=TrackerFormat.IT)
    another_xm_module = _build_module(format(3, "064x"), repository.next_id(), tracker=TrackerFormat.XM)
    for module in (xm_module, it_module, another_xm_module):
        repository.insert(module)

    return xm_module, it_module, another_xm_module


def test_list_page_orders_by_id_and_respects_limit_and_offset(connection: duckdb.DuckDBPyConnection) -> None:
    repository = DuckDBModuleRepository(connection)
    first, second, third = _insert_three_modules(repository)

    assert repository.list_page(limit=2, offset=0) == (first, second)
    assert repository.list_page(limit=2, offset=2) == (third,)


def test_list_page_filters_by_tracker(connection: duckdb.DuckDBPyConnection) -> None:
    repository = DuckDBModuleRepository(connection)
    first, _, third = _insert_three_modules(repository)

    assert repository.list_page(limit=10, offset=0, tracker=TrackerFormat.XM) == (first, third)


def test_get_many_returns_only_the_requested_hashes_that_exist(connection: duckdb.DuckDBPyConnection) -> None:
    repository = DuckDBModuleRepository(connection)
    first, _, third = _insert_three_modules(repository)

    result = repository.get_many([first.hash, format(9, "064x")])

    assert result == {first.hash: first}
    assert third.hash not in result


def test_get_many_with_no_hashes_returns_nothing(connection: duckdb.DuckDBPyConnection) -> None:
    assert DuckDBModuleRepository(connection).get_many([]) == {}


def test_count_matches_the_number_of_stored_modules(connection: duckdb.DuckDBPyConnection) -> None:
    repository = DuckDBModuleRepository(connection)
    _insert_three_modules(repository)

    assert repository.count() == 3
    assert repository.count(tracker=TrackerFormat.IT) == 1
