from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final, Protocol

from sqlalchemy import Connection, Row, func, select
from trackmod.core.notes.pitch import Note

from samplecore.models.note_event import NoteEvent, SampleNoteUsage
from samplecore.storage.database import bulk_insert, note_event, sample_properties

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

    def note_usage_for_sample(self, sample_hash: str) -> tuple[SampleNoteUsage, ...]: ...

    def dominant_note_by_hash(self, hashes: list[str]) -> dict[str, Note]: ...


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

    def note_usage_for_sample(self, sample_hash: str) -> tuple[SampleNoteUsage, ...]:
        """Every note one sample is heard at, with how many events reach it, lowest note first.

        A sample is reached through the occurrences that name it, so the count gathers every module
        playing the same waveform into one picture of the pitches it is used at.
        """
        # pylint: disable-next=not-callable
        event_count = func.count().label("event_count")
        statement = (
            select(note_event.c.sounded_note, event_count)
            .select_from(
                note_event.join(
                    sample_properties,
                    (sample_properties.c.module_id == note_event.c.module_id)
                    & (sample_properties.c.instrument_index == note_event.c.instrument_index)
                    & (sample_properties.c.sample_slot == note_event.c.sample_slot),
                )
            )
            .where(sample_properties.c.sample_hash == sample_hash)
            .group_by(note_event.c.sounded_note)
            .order_by(note_event.c.sounded_note)
        )
        rows = self._connection.execute(statement).fetchall()
        return tuple(SampleNoteUsage(sounded_note=Note(row.sounded_note), event_count=row.event_count) for row in rows)

    def dominant_note_by_hash(self, hashes: list[str]) -> dict[str, Note]:
        """The note each given sample is played at most often, ties going to the lower note.

        This is the pitch a preview should open at: a sample's stored rate only says what it sounds
        like at C-5, while the note says where the library actually puts it.
        """
        if not hashes:
            return {}

        # pylint: disable-next=not-callable
        event_count = func.count().label("event_count")
        ranking = (
            select(
                sample_properties.c.sample_hash,
                note_event.c.sounded_note,
                func.row_number()
                .over(
                    partition_by=sample_properties.c.sample_hash,
                    order_by=(event_count.desc(), note_event.c.sounded_note.asc()),
                )
                .label("rank"),
            )
            .select_from(
                note_event.join(
                    sample_properties,
                    (sample_properties.c.module_id == note_event.c.module_id)
                    & (sample_properties.c.instrument_index == note_event.c.instrument_index)
                    & (sample_properties.c.sample_slot == note_event.c.sample_slot),
                )
            )
            .where(sample_properties.c.sample_hash.in_(hashes))
            .group_by(sample_properties.c.sample_hash, note_event.c.sounded_note)
            .subquery()
        )
        statement = select(ranking.c.sample_hash, ranking.c.sounded_note).where(ranking.c.rank == 1)
        rows = self._connection.execute(statement).fetchall()
        return {row.sample_hash: Note(row.sounded_note) for row in rows}


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
