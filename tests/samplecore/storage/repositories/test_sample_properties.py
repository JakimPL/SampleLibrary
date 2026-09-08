from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import Connection
from trackmod.core.samples.loop import Loop, LoopMode
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.module import Module
from samplecore.models.sample import Sample
from samplecore.models.sample_properties import (
    ITSampleProperties,
    MODSampleProperties,
    S3MSampleProperties,
    SampleOccurrence,
    Vibrato,
    XMSampleProperties,
)
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.sample_properties import (
    PostgresSamplePropertiesRepository,
    _loop_from_row,
    _vibrato_from_row,
)


def _xm_properties(module_hash: str, sample_hash: str, *, sample_slot: int) -> XMSampleProperties:
    return XMSampleProperties(
        sample_hash=sample_hash,
        occurrence=SampleOccurrence(module_hash=module_hash, instrument_index=0, sample_slot=sample_slot),
        name="lead",
        rate=8363,
        volume=64,
        loop=Loop(begin=0, end=4, mode=LoopMode.FORWARD),
        tuning=Tuning(relative_note=0, finetune=0),
    )


def _it_properties(module_hash: str, sample_hash: str, *, sample_slot: int) -> ITSampleProperties:
    return ITSampleProperties(
        sample_hash=sample_hash,
        occurrence=SampleOccurrence(module_hash=module_hash, instrument_index=1, sample_slot=sample_slot),
        name="kick",
        rate=8363,
        volume=64,
        global_volume=64,
        sustain_loop=Loop(begin=1, end=3, mode=LoopMode.PING_PONG),
        filename="KICK.WAV",
        vibrato=Vibrato(speed=1, depth=2, rate=3, waveform=0),
    )


def _mod_properties(module_hash: str, sample_hash: str, *, sample_slot: int) -> MODSampleProperties:
    return MODSampleProperties(
        sample_hash=sample_hash,
        occurrence=SampleOccurrence(module_hash=module_hash, instrument_index=0, sample_slot=sample_slot),
        name="chip",
        rate=8363,
        volume=64,
    )


def _s3m_properties(module_hash: str, sample_hash: str, *, sample_slot: int) -> S3MSampleProperties:
    return S3MSampleProperties(
        sample_hash=sample_hash,
        occurrence=SampleOccurrence(module_hash=module_hash, instrument_index=0, sample_slot=sample_slot),
        name="pluck",
        rate=8363,
        volume=64,
        filename="PLUCK.S3I",
    )


def test_mod_properties_round_trip_through_list_for_module(
    connection: Connection, stored_module: Module, stored_sample: Sample
) -> None:
    repository = PostgresSamplePropertiesRepository(connection)
    properties = _mod_properties(stored_module.hash, stored_sample.hash, sample_slot=0)

    repository.upsert(properties)

    assert repository.list_for_module(stored_module.hash) == (properties,)


def test_s3m_properties_round_trip_with_filename_left_unset(
    connection: Connection, stored_module: Module, stored_sample: Sample
) -> None:
    repository = PostgresSamplePropertiesRepository(connection)
    properties = S3MSampleProperties(
        sample_hash=stored_sample.hash,
        occurrence=SampleOccurrence(module_hash=stored_module.hash, instrument_index=0, sample_slot=0),
        name="pluck",
        rate=8363,
        volume=64,
    )

    repository.upsert(properties)

    round_tripped = repository.list_for_module(stored_module.hash)[0]
    assert isinstance(round_tripped, S3MSampleProperties)
    assert round_tripped.filename is None


def test_xm_properties_round_trip_through_list_for_module(
    connection: Connection, stored_module: Module, stored_sample: Sample
) -> None:
    repository = PostgresSamplePropertiesRepository(connection)
    properties = _xm_properties(stored_module.hash, stored_sample.hash, sample_slot=0)

    repository.upsert(properties)

    assert repository.list_for_module(stored_module.hash) == (properties,)


def test_it_properties_round_trip_with_optional_fields_populated(
    connection: Connection, stored_module: Module, stored_sample: Sample
) -> None:
    repository = PostgresSamplePropertiesRepository(connection)
    properties = _it_properties(stored_module.hash, stored_sample.hash, sample_slot=0)

    repository.upsert(properties)

    assert repository.list_for_module(stored_module.hash) == (properties,)


def test_it_properties_round_trip_with_optional_fields_left_unset(
    connection: Connection, stored_module: Module, stored_sample: Sample
) -> None:
    repository = PostgresSamplePropertiesRepository(connection)
    properties = ITSampleProperties(
        sample_hash=stored_sample.hash,
        occurrence=SampleOccurrence(module_hash=stored_module.hash, instrument_index=0, sample_slot=0),
        name="snare",
        rate=8363,
        volume=64,
        global_volume=64,
    )

    repository.upsert(properties)

    round_tripped = repository.list_for_module(stored_module.hash)[0]
    assert isinstance(round_tripped, ITSampleProperties)
    assert round_tripped.sustain_loop is None
    assert round_tripped.filename is None
    assert round_tripped.vibrato is None


def test_properties_for_different_instruments_are_returned_ordered(
    connection: Connection, stored_module: Module, stored_sample: Sample
) -> None:
    repository = PostgresSamplePropertiesRepository(connection)
    xm_properties = _xm_properties(stored_module.hash, stored_sample.hash, sample_slot=0)
    it_properties = _it_properties(stored_module.hash, stored_sample.hash, sample_slot=0)

    repository.upsert(it_properties)
    repository.upsert(xm_properties)

    ordered = repository.list_for_module(stored_module.hash)
    assert ordered == (xm_properties, it_properties)


def test_upserting_properties_for_an_unknown_module_raises(connection: Connection, stored_sample: Sample) -> None:
    repository = PostgresSamplePropertiesRepository(connection)
    properties = _xm_properties("f" * 64, stored_sample.hash, sample_slot=0)

    with pytest.raises(ValueError, match="no module ingested"):
        repository.upsert(properties)


def test_a_partially_populated_loop_is_rejected_as_inconsistent() -> None:
    with pytest.raises(ValueError, match="set together"):
        _loop_from_row(0, None, "forward")


def test_a_partially_populated_vibrato_is_rejected_as_inconsistent() -> None:
    with pytest.raises(ValueError, match="set together"):
        _vibrato_from_row(1, 2, None, 0)


def test_list_for_sample_finds_occurrences_across_different_modules(
    connection: Connection, stored_module: Module, stored_sample: Sample
) -> None:
    other_module_repository = PostgresModuleRepository(connection)
    other_module = Module(
        hash=format(99, "064x"),
        id=other_module_repository.next_id(),
        filename="other.xm",
        tracker=TrackerFormat.XM,
        title="other",
        channel_count=4,
        pattern_count=1,
        instrument_count=1,
        sample_count=1,
        file_size=1024,
        ingested_at=datetime.now(UTC),
    )
    other_module_repository.insert(other_module)

    repository = PostgresSamplePropertiesRepository(connection)
    first_occurrence = _xm_properties(stored_module.hash, stored_sample.hash, sample_slot=0)
    second_occurrence = _it_properties(other_module.hash, stored_sample.hash, sample_slot=0)
    repository.upsert(first_occurrence)
    repository.upsert(second_occurrence)

    assert set(repository.list_for_sample(stored_sample.hash)) == {first_occurrence, second_occurrence}


def test_cataloged_slots_reports_every_occurrence_a_module_holds(
    connection: Connection, stored_sample: Sample, stored_module: Module
) -> None:
    repository = PostgresSamplePropertiesRepository(connection)
    repository.upsert(_xm_properties(stored_module.hash, stored_sample.hash, sample_slot=0))
    repository.upsert(_it_properties(stored_module.hash, stored_sample.hash, sample_slot=3))

    assert repository.cataloged_slots(stored_module.id) == frozenset({(0, 0), (1, 3)})


def test_cataloged_slots_for_a_module_with_no_occurrences_returns_nothing(
    connection: Connection, stored_module: Module
) -> None:
    assert PostgresSamplePropertiesRepository(connection).cataloged_slots(stored_module.id) == frozenset()


def test_list_for_sample_finds_nothing_for_an_unreferenced_sample(connection: Connection, sample_hash_b: str) -> None:
    assert PostgresSamplePropertiesRepository(connection).list_for_sample(sample_hash_b) == ()
