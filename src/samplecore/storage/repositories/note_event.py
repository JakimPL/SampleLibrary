from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final, Protocol

from sqlalchemy import Connection, Row, func, select
from trackmod.core.notes.pitch import Note

from samplecore.models.note_event import NoteEvent
from samplecore.storage.database import bulk_insert, note_event

_COLUMN_NAMES: Final[tuple[str, ...]] = (
    "module_id",
    "pattern_index",
    "row_index",
    "channel_index",
    "note",
    "sounded_note",
    "instrument_index",
    "sample_slot",
)


class NoteEventRepository(Protocol):
    """Persistence for the notes a module's patterns play: one row per key a cell presses."""

    def insert_many(self, events: Sequence[NoteEvent]) -> None: ...

    def list_for_module(self, module_id: int) -> tuple[NoteEvent, ...]: ...

    def delete_for_module(self, module_id: int) -> None: ...

    def count(self) -> int: ...


class PostgresNoteEventRepository:
    """A NoteEventRepository backed by the catalog's ``note_event`` table.

    ``insert_many`` writes through Postgres's own bulk loader and states no conflict resolution: a
    module's events are written once, inside the transaction that reads its patterns, and a module
    already on file is either skipped by the pass or cleared through ``delete_for_module`` first.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def insert_many(self, events: Sequence[NoteEvent]) -> None:
        if not events:
            return

        bulk_insert(
            self._connection,
            note_event,
            _COLUMN_NAMES,
            (
                (
                    event.module_id,
                    event.pattern_index,
                    event.row_index,
                    event.channel_index,
                    event.note.value,
                    None if event.sounded_note is None else event.sounded_note.value,
                    event.instrument_index,
                    event.sample_slot,
                )
                for event in events
            ),
        )

    def list_for_module(self, module_id: int) -> tuple[NoteEvent, ...]:
        statement = (
            select(note_event)
            .where(note_event.c.module_id == module_id)
            .order_by(note_event.c.pattern_index, note_event.c.row_index, note_event.c.channel_index)
        )
        rows = self._connection.execute(statement).fetchall()
        return tuple(_row_to_note_event(row) for row in rows)

    def delete_for_module(self, module_id: int) -> None:
        self._connection.execute(note_event.delete().where(note_event.c.module_id == module_id))

    def count(self) -> int:
        # pylint: disable-next=not-callable
        return self._connection.execute(select(func.count()).select_from(note_event)).scalar_one()


def _row_to_note_event(row: Row[Any]) -> NoteEvent:
    """Reconstruct a NoteEvent from a Core row, addressed by its own column names."""
    return NoteEvent(
        module_id=row.module_id,
        pattern_index=row.pattern_index,
        row_index=row.row_index,
        channel_index=row.channel_index,
        note=Note(row.note),
        sounded_note=None if row.sounded_note is None else Note(row.sounded_note),
        instrument_index=row.instrument_index,
        sample_slot=row.sample_slot,
    )
