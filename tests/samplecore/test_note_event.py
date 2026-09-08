from __future__ import annotations

import pytest
from pydantic import ValidationError
from trackmod.core.notes.pitch import Note
from trackmod.spec.pitch import NOTE_COUNT

from samplecore.models.note_event import NoteEvent

PRESSED_NOTE = Note(60)


def _note_event(*, sounded_note: Note | None, instrument_index: int | None, sample_slot: int | None) -> NoteEvent:
    return NoteEvent(
        module_id=1,
        pattern_index=0,
        row_index=0,
        channel_index=0,
        note=PRESSED_NOTE,
        sounded_note=sounded_note,
        instrument_index=instrument_index,
        sample_slot=sample_slot,
    )


def test_an_event_resolved_through_an_instrument_is_accepted() -> None:
    event = _note_event(sounded_note=Note(72), instrument_index=0, sample_slot=0)

    assert event.sounded_note == Note(72)


def test_an_event_naming_no_instrument_leaves_its_routing_open() -> None:
    event = _note_event(sounded_note=None, instrument_index=None, sample_slot=None)

    assert event.sounded_note is None
    assert event.sample_slot is None


def test_a_resolved_note_without_an_instrument_is_refused() -> None:
    with pytest.raises(ValidationError, match="requires the instrument index"):
        _note_event(sounded_note=PRESSED_NOTE, instrument_index=None, sample_slot=None)


def test_a_sample_slot_without_an_instrument_is_refused() -> None:
    with pytest.raises(ValidationError, match="requires the instrument index"):
        _note_event(sounded_note=None, instrument_index=None, sample_slot=0)


def test_a_value_past_the_key_range_is_refused() -> None:
    """A note column spells key-off, cut and fade past the highest key, and none of those is an event."""
    with pytest.raises(ValidationError):
        NoteEvent(
            module_id=1,
            pattern_index=0,
            row_index=0,
            channel_index=0,
            note=NOTE_COUNT,
            sounded_note=None,
            instrument_index=None,
            sample_slot=None,
        )
