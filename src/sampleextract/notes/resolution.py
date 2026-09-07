from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from trackmod.core.notes.pitch import Note
from trackmod.core.patterns.grid import Pattern
from trackmod.core.songs.song import Song
from trackmod.core.voices.voices import InstrumentVoices
from trackmod.spec.grid import EMPTY
from trackmod.spec.pitch import NOTE_COUNT

from samplecore.models.module_instrument import ModuleInstrument
from samplecore.models.note_event import NoteEvent
from sampleextract.voices import addressable_voices

SampleSlots = tuple[dict[int, int], ...]


def resolve_module_instruments(song: Song, *, module_id: int) -> tuple[ModuleInstrument, ...]:
    """Every instrument slot the song's voice table numbers, in that table's own order."""
    voices = addressable_voices(song)
    return tuple(
        ModuleInstrument(
            module_id=module_id,
            instrument_index=instrument_index,
            name=instrument.name,
            fadeout=instrument.fadeout,
            global_volume=instrument.global_volume,
            panning=instrument.panning,
            new_note_action=instrument.new_note_action,
            duplicate_check=instrument.duplicate_check,
            duplicate_action=instrument.duplicate_action,
        )
        for instrument_index, instrument in enumerate(voices.instruments)
    )


def resolve_note_events(
    song: Song, *, module_id: int, catalogued_slots: frozenset[tuple[int, int]]
) -> tuple[NoteEvent, ...]:
    """Every key the song's patterns press, carrying the note and sample its instrument routes it to.

    ``catalogued_slots`` states which occurrences the catalog holds for this module, so a key routed
    onto a sample it left out resolves to a note with an open slot: the event stays on record, and
    every slot named is one the catalog can actually be joined to.
    """
    voices = addressable_voices(song)
    sample_slots = _sample_slots(voices, catalogued_slots=catalogued_slots)
    events: list[NoteEvent] = []
    for pattern_index, pattern in enumerate(song.patterns):
        events.extend(
            _pattern_note_events(
                pattern, module_id=module_id, pattern_index=pattern_index, voices=voices, sample_slots=sample_slots
            )
        )

    return tuple(events)


def _sample_slots(voices: InstrumentVoices, *, catalogued_slots: frozenset[tuple[int, int]]) -> SampleSlots:
    """Per instrument, the catalog slot each sample its keys reach is stored under.

    ``held`` numbers an instrument's samples from zero in the order its keys first name them, which
    is the numbering ``sample_properties`` records and a different space from the song-wide sample
    table a keymap indexes into. A slot the catalog holds no occurrence for is absent here, which is
    what marks a key routed onto it as reaching no stored occurrence.
    """
    return tuple(
        {
            sample_index: slot
            for slot, sample_index in enumerate(instrument.samples)
            if (instrument_index, slot) in catalogued_slots
        }
        for instrument_index, instrument in enumerate(voices.instruments)
    )


def _pattern_note_events(
    pattern: Pattern, *, module_id: int, pattern_index: int, voices: InstrumentVoices, sample_slots: SampleSlots
) -> list[NoteEvent]:
    """Every note event one pattern's grid holds, read off its planes rather than cell by cell."""
    notes: NDArray[np.int16] = np.asarray(pattern.note)
    instruments: NDArray[np.int16] = np.asarray(pattern.instrument)
    pressed = (notes >= 0) & (notes < NOTE_COUNT)
    rows, channels = pressed.nonzero()
    return [
        _note_event(
            module_id=module_id,
            pattern_index=pattern_index,
            row_index=int(row_index),
            channel_index=int(channel_index),
            note=Note(int(notes[row_index, channel_index])),
            instrument_index=_stated_instrument(int(instruments[row_index, channel_index])),
            voices=voices,
            sample_slots=sample_slots,
        )
        for row_index, channel_index in zip(rows, channels)
    ]


def _stated_instrument(instrument_value: int) -> int | None:
    return None if instrument_value == EMPTY else instrument_value


# Each keyword below is an independent fact about the one grid position being resolved, and the two
# lookup tables it is resolved against; the group has no natural subdivision.
# pylint: disable-next=too-many-arguments
def _note_event(
    *,
    module_id: int,
    pattern_index: int,
    row_index: int,
    channel_index: int,
    note: Note,
    instrument_index: int | None,
    voices: InstrumentVoices,
    sample_slots: SampleSlots,
) -> NoteEvent:
    sounded_note, sample_slot = _routing(note, instrument_index=instrument_index, voices=voices, slots=sample_slots)
    return NoteEvent(
        module_id=module_id,
        pattern_index=pattern_index,
        row_index=row_index,
        channel_index=channel_index,
        note=note,
        sounded_note=sounded_note,
        instrument_index=instrument_index,
        sample_slot=sample_slot,
    )


def _routing(
    note: Note, *, instrument_index: int | None, voices: InstrumentVoices, slots: SampleSlots
) -> tuple[Note | None, int | None]:
    """The note a key sounds and the catalog slot it reaches, as far as the cell states them.

    A cell naming no instrument leaves the routing to whichever instrument its channel already
    carries, which is a fact about how the song is played rather than what the cell holds, so both
    values stay open. A key its instrument's keymap leaves silent resolves to neither.
    """
    if instrument_index is None:
        return None, None

    assignment = voices.instruments[instrument_index].assignment(note)
    if assignment is None:
        return None, None

    return assignment.note, slots[instrument_index].get(assignment.sample)
