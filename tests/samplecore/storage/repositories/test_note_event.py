from __future__ import annotations

import psycopg
import pytest
from sqlalchemy import Connection
from trackmod.core.notes.pitch import Note
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.module import Module
from samplecore.models.note_event import NoteEvent
from samplecore.models.sample import Sample
from samplecore.models.sample_properties import SampleOccurrence, XMSampleProperties
from samplecore.storage.repositories.note_event import PostgresNoteEventRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository

PRESSED_NOTE = Note(60)
SOUNDED_NOTE = Note(72)


def _note_event(
    module: Module,
    *,
    pattern_index: int = 0,
    row_index: int = 0,
    channel_index: int = 0,
    instrument_index: int | None = 0,
    sample_slot: int | None = 0,
    sounded_note: Note | None = SOUNDED_NOTE,
) -> NoteEvent:
    return NoteEvent(
        module_id=module.id,
        pattern_index=pattern_index,
        row_index=row_index,
        channel_index=channel_index,
        note=PRESSED_NOTE,
        sounded_note=sounded_note,
        instrument_index=instrument_index,
        sample_slot=sample_slot,
    )


@pytest.fixture
def stored_occurrence(connection: Connection, stored_sample: Sample, stored_module: Module) -> None:
    PostgresSamplePropertiesRepository(connection).upsert(
        XMSampleProperties(
            sample_hash=stored_sample.hash,
            occurrence=SampleOccurrence(module_hash=stored_module.hash, instrument_index=0, sample_slot=0),
            name="bell",
            rate=8363,
            volume=64,
            tuning=Tuning(relative_note=0, finetune=0),
        )
    )


def test_a_stored_note_event_round_trips_through_list_for_module(
    connection: Connection, stored_module: Module, stored_occurrence: None
) -> None:
    repository = PostgresNoteEventRepository(connection)
    event = _note_event(stored_module)

    repository.insert_many([event])

    assert repository.list_for_module(stored_module.id) == (event,)


def test_list_for_module_orders_events_by_their_grid_position(
    connection: Connection, stored_module: Module, stored_occurrence: None
) -> None:
    repository = PostgresNoteEventRepository(connection)
    last = _note_event(stored_module, pattern_index=1, row_index=0, channel_index=0)
    middle = _note_event(stored_module, pattern_index=0, row_index=4, channel_index=0)
    first = _note_event(stored_module, pattern_index=0, row_index=0, channel_index=3)

    repository.insert_many([last, middle, first])

    assert repository.list_for_module(stored_module.id) == (first, middle, last)


def test_an_event_reaching_no_catalogued_occurrence_keeps_its_resolved_note(
    connection: Connection, stored_module: Module
) -> None:
    repository = PostgresNoteEventRepository(connection)
    event = _note_event(stored_module, sample_slot=None)

    repository.insert_many([event])

    assert repository.list_for_module(stored_module.id) == (event,)


def test_an_event_whose_cell_names_no_instrument_is_stored_unresolved(
    connection: Connection, stored_module: Module
) -> None:
    repository = PostgresNoteEventRepository(connection)
    event = _note_event(stored_module, instrument_index=None, sample_slot=None, sounded_note=None)

    repository.insert_many([event])

    assert repository.list_for_module(stored_module.id) == (event,)


def test_inserting_no_events_leaves_the_table_untouched(connection: Connection, stored_module: Module) -> None:
    repository = PostgresNoteEventRepository(connection)

    repository.insert_many([])

    assert repository.list_for_module(stored_module.id) == ()


def test_list_for_module_on_a_module_with_no_events_returns_nothing(
    connection: Connection, stored_module: Module
) -> None:
    assert PostgresNoteEventRepository(connection).list_for_module(stored_module.id) == ()


def test_an_event_naming_an_occurrence_the_catalog_lacks_is_refused(
    connection: Connection, stored_module: Module
) -> None:
    repository = PostgresNoteEventRepository(connection)

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        repository.insert_many([_note_event(stored_module, sample_slot=7)])


def test_delete_for_module_removes_only_that_module_s_events(
    connection: Connection, stored_module: Module, stored_module_b: Module, stored_occurrence: None
) -> None:
    repository = PostgresNoteEventRepository(connection)
    kept = _note_event(stored_module_b, instrument_index=None, sample_slot=None, sounded_note=None)
    repository.insert_many([_note_event(stored_module), kept])

    repository.delete_for_module(stored_module.id)

    assert repository.list_for_module(stored_module.id) == ()
    assert repository.list_for_module(stored_module_b.id) == (kept,)


def test_count_reflects_every_stored_event(
    connection: Connection, stored_module: Module, stored_occurrence: None
) -> None:
    repository = PostgresNoteEventRepository(connection)
    repository.insert_many([_note_event(stored_module), _note_event(stored_module, row_index=1)])

    assert repository.count() == 2


def test_note_usage_counts_the_events_reaching_a_sample_at_each_note(
    connection: Connection, stored_sample: Sample, stored_module: Module, stored_occurrence: None
) -> None:
    repository = PostgresNoteEventRepository(connection)
    repository.insert_many(
        [
            _note_event(stored_module, row_index=0, sounded_note=SOUNDED_NOTE),
            _note_event(stored_module, row_index=1, sounded_note=SOUNDED_NOTE),
            _note_event(stored_module, row_index=2, sounded_note=PRESSED_NOTE),
        ]
    )

    usage = repository.note_usage_for_sample(stored_sample.hash)

    assert [(item.sounded_note, item.event_count) for item in usage] == [(PRESSED_NOTE, 1), (SOUNDED_NOTE, 2)]


def test_note_usage_leaves_out_an_event_reaching_no_catalogued_occurrence(
    connection: Connection, stored_sample: Sample, stored_module: Module, stored_occurrence: None
) -> None:
    repository = PostgresNoteEventRepository(connection)
    repository.insert_many(
        [
            _note_event(stored_module, row_index=0),
            _note_event(stored_module, row_index=1, sample_slot=None),
        ]
    )

    usage = repository.note_usage_for_sample(stored_sample.hash)

    assert [item.event_count for item in usage] == [1]


def test_note_usage_for_a_sample_no_pattern_plays_returns_nothing(
    connection: Connection, stored_sample: Sample, stored_occurrence: None
) -> None:
    assert PostgresNoteEventRepository(connection).note_usage_for_sample(stored_sample.hash) == ()
