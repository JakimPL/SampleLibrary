from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.module import Module
from samplecore.models.sample import Sample
from samplecore.models.sample_properties import MODSampleProperties, SampleOccurrence
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository

_SHARED_SAMPLE_HASH = "a" * 64


def _catalogue_one_sample(connection: Connection, module_: Module) -> None:
    """Give a module the sample occurrence that makes it worth browsing to."""
    PostgresSampleRepository(connection).upsert(
        Sample(hash=_SHARED_SAMPLE_HASH, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
    )
    PostgresSamplePropertiesRepository(connection).upsert(
        MODSampleProperties(
            sample_hash=_SHARED_SAMPLE_HASH,
            occurrence=SampleOccurrence(module_hash=module_.hash, instrument_index=0, sample_slot=0),
            name="smp01",
            rate=8363,
            volume=64,
        )
    )


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


def test_a_stored_module_round_trips_through_get(connection: Connection, module_hash_a: str) -> None:
    repository = PostgresModuleRepository(connection)
    module = _build_module(module_hash_a, repository.next_id())

    repository.insert(module)

    assert repository.get(module_hash_a) == module


def test_get_on_an_unknown_hash_returns_none(connection: Connection, module_hash_a: str) -> None:
    repository = PostgresModuleRepository(connection)

    assert repository.get(module_hash_a) is None


def test_next_id_produces_increasing_values(connection: Connection) -> None:
    repository = PostgresModuleRepository(connection)

    first_id = repository.next_id()
    second_id = repository.next_id()

    assert second_id > first_id


def _insert_three_modules(
    repository: PostgresModuleRepository, connection: Connection
) -> tuple[Module, Module, Module]:
    xm_module = _build_module(format(1, "064x"), repository.next_id(), tracker=TrackerFormat.XM)
    it_module = _build_module(format(2, "064x"), repository.next_id(), tracker=TrackerFormat.IT)
    another_xm_module = _build_module(format(3, "064x"), repository.next_id(), tracker=TrackerFormat.XM)
    for module in (xm_module, it_module, another_xm_module):
        repository.insert(module)
        _catalogue_one_sample(connection, module)

    return xm_module, it_module, another_xm_module


def test_list_all_on_an_empty_catalog_returns_nothing(connection: Connection) -> None:
    assert PostgresModuleRepository(connection).list_all() == ()


def test_list_all_returns_every_stored_module(connection: Connection) -> None:
    repository = PostgresModuleRepository(connection)
    first, second, third = _insert_three_modules(repository, connection)

    assert set(repository.list_all()) == {first, second, third}


def test_list_page_orders_by_id_and_respects_limit_and_offset(connection: Connection) -> None:
    repository = PostgresModuleRepository(connection)
    first, second, third = _insert_three_modules(repository, connection)

    assert repository.list_page(limit=2, offset=0) == (first, second)
    assert repository.list_page(limit=2, offset=2) == (third,)


def test_list_page_filters_by_tracker(connection: Connection) -> None:
    repository = PostgresModuleRepository(connection)
    first, _, third = _insert_three_modules(repository, connection)

    assert repository.list_page(limit=10, offset=0, tracker=TrackerFormat.XM) == (first, third)


def test_get_many_returns_only_the_requested_hashes_that_exist(connection: Connection) -> None:
    repository = PostgresModuleRepository(connection)
    first, _, third = _insert_three_modules(repository, connection)

    result = repository.get_many([first.hash, format(9, "064x")])

    assert result == {first.hash: first}
    assert third.hash not in result


def test_get_many_with_no_hashes_returns_nothing(connection: Connection) -> None:
    assert PostgresModuleRepository(connection).get_many([]) == {}


def test_count_matches_the_number_of_stored_modules(connection: Connection) -> None:
    repository = PostgresModuleRepository(connection)
    _insert_three_modules(repository, connection)

    assert repository.count() == 3
    assert repository.count(tracker=TrackerFormat.IT) == 1


def test_a_module_the_catalog_holds_no_sample_from_is_left_out_of_the_listing(connection: Connection) -> None:
    """A chiptune whose every waveform is too short to catalogue has nothing to show a reader."""
    repository = PostgresModuleRepository(connection)
    first, _, _ = _insert_three_modules(repository, connection)
    chiptune = _build_module(format(4, "064x"), repository.next_id())
    repository.insert(chiptune)

    listed = repository.list_page(limit=10, offset=0)

    assert chiptune not in listed
    assert first in listed
    assert repository.count() == 3


def test_a_module_left_out_of_the_listing_stays_catalogued_and_reachable(connection: Connection) -> None:
    """Keeping the module is the point: only browsing past it is noise."""
    repository = PostgresModuleRepository(connection)
    chiptune = _build_module(format(4, "064x"), repository.next_id())
    repository.insert(chiptune)

    assert repository.get(chiptune.hash) == chiptune
    assert repository.list_all() == (chiptune,)
