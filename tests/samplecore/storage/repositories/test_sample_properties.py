from __future__ import annotations

import duckdb
import pytest
from trackmod.core.samples.loop import Loop, LoopMode
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.module import Module
from samplecore.models.sample import Sample
from samplecore.models.sample_properties import (
    ITSampleProperties,
    SampleOccurrence,
    Vibrato,
    XMSampleProperties,
)
from samplecore.storage.repositories.sample_properties import (
    DuckDBSamplePropertiesRepository,
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


def test_xm_properties_round_trip_through_list_for_module(
    connection: duckdb.DuckDBPyConnection, stored_module: Module, stored_sample: Sample
) -> None:
    repository = DuckDBSamplePropertiesRepository(connection)
    properties = _xm_properties(stored_module.hash, stored_sample.hash, sample_slot=0)

    repository.upsert(properties)

    assert repository.list_for_module(stored_module.hash) == (properties,)


def test_it_properties_round_trip_with_optional_fields_populated(
    connection: duckdb.DuckDBPyConnection, stored_module: Module, stored_sample: Sample
) -> None:
    repository = DuckDBSamplePropertiesRepository(connection)
    properties = _it_properties(stored_module.hash, stored_sample.hash, sample_slot=0)

    repository.upsert(properties)

    assert repository.list_for_module(stored_module.hash) == (properties,)


def test_it_properties_round_trip_with_optional_fields_left_unset(
    connection: duckdb.DuckDBPyConnection, stored_module: Module, stored_sample: Sample
) -> None:
    repository = DuckDBSamplePropertiesRepository(connection)
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
    connection: duckdb.DuckDBPyConnection, stored_module: Module, stored_sample: Sample
) -> None:
    repository = DuckDBSamplePropertiesRepository(connection)
    xm_properties = _xm_properties(stored_module.hash, stored_sample.hash, sample_slot=0)
    it_properties = _it_properties(stored_module.hash, stored_sample.hash, sample_slot=0)

    repository.upsert(it_properties)
    repository.upsert(xm_properties)

    ordered = repository.list_for_module(stored_module.hash)
    assert ordered == (xm_properties, it_properties)


def test_upserting_properties_for_an_unknown_module_raises(
    connection: duckdb.DuckDBPyConnection, stored_sample: Sample
) -> None:
    repository = DuckDBSamplePropertiesRepository(connection)
    properties = _xm_properties("f" * 64, stored_sample.hash, sample_slot=0)

    with pytest.raises(ValueError, match="no module ingested"):
        repository.upsert(properties)


def test_a_partially_populated_loop_is_rejected_as_inconsistent() -> None:
    with pytest.raises(ValueError, match="set together"):
        _loop_from_row(0, None, "forward")


def test_a_partially_populated_vibrato_is_rejected_as_inconsistent() -> None:
    with pytest.raises(ValueError, match="set together"):
        _vibrato_from_row(1, 2, None, 0)
