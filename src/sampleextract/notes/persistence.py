from __future__ import annotations

from datetime import datetime

from sqlalchemy import Connection
from trackmod.core.songs.song import Song

from samplecore.models.note_extraction import ModuleNoteExtraction
from samplecore.storage.repositories.module_instrument import PostgresModuleInstrumentRepository
from samplecore.storage.repositories.note_event import PostgresNoteEventRepository
from samplecore.storage.repositories.note_extraction import PostgresModuleNoteExtractionRepository
from sampleextract.notes.resolution import resolve_module_instruments, resolve_note_events


def persist_module_notes(
    connection: Connection, *, song: Song, module_id: int, extracted_at: datetime, minimum_sample_frames: int
) -> int:
    """Record one module's instrument slots and the notes its patterns play, and mark it read.

    The caller owns the transaction, so this joins whatever ingest or a backfill pass already has
    open and the whole module lands or none of it does. Returns how many note events were written,
    which is what a pass reports on.

    A module whose rows are already on file is cleared through ``clear_module_notes`` first.
    """
    events = resolve_note_events(song, module_id=module_id, minimum_sample_frames=minimum_sample_frames)
    PostgresModuleInstrumentRepository(connection).insert_many(resolve_module_instruments(song, module_id=module_id))
    PostgresNoteEventRepository(connection).insert_many(events)
    PostgresModuleNoteExtractionRepository(connection).mark(
        ModuleNoteExtraction(module_id=module_id, extracted_at=extracted_at)
    )
    return len(events)


def clear_module_notes(connection: Connection, *, module_id: int) -> None:
    """Remove everything a previous read of one module's patterns left behind.

    Note events reference the instrument slots they were routed through, so they go first.
    """
    PostgresNoteEventRepository(connection).delete_for_module(module_id)
    PostgresModuleInstrumentRepository(connection).delete_for_module(module_id)
    PostgresModuleNoteExtractionRepository(connection).delete_for_module(module_id)
