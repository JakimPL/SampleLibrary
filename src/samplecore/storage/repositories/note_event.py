from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any, Final, Protocol

from sqlalchemy import Connection, Row, Select, func, select
from trackmod.core.notes.pitch import Note

from samplecore.models.note_event import NoteEvent, SampleNoteStatistics, SampleNoteUsage
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

# How many grouped rows one server-side batch of a whole-catalog usage stream carries. Large enough
# that the round trips disappear against the aggregate itself, small enough to stay a rounding error
# in the folding caller's memory.
_USAGE_BATCH_SIZE: Final[int] = 10_000


class NoteEventRepository(Protocol):
    """Persistence for the notes a module's patterns play: one row per key a cell presses."""

    def insert_many(self, events: Sequence[NoteEvent]) -> None: ...

    def list_for_module(self, module_id: int) -> tuple[NoteEvent, ...]: ...

    def delete_for_module(self, module_id: int) -> None: ...

    def count(self) -> int: ...

    def note_usage_for_sample(self, sample_hash: str) -> tuple[SampleNoteUsage, ...]: ...

    def note_usage_for_every_sample(self) -> Iterator[tuple[str, SampleNoteUsage]]: ...

    def note_statistics_for_every_sample(self) -> dict[str, SampleNoteStatistics]: ...


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
        """Every rate-and-note pair one sample is heard at, with how many events reach it.

        A sample is reached through the occurrences that name it, so the count gathers every module
        playing the same waveform into one picture of how it is used. Each occurrence declares a rate
        of its own, and the same key struck against two of them sounds two different speeds, so the
        rate stays joined to the note it was struck against all the way out of the query. Ordered by
        rate and then note, which walks a sample's occurrences one at a time.
        """
        statement = self._usage_statement().where(sample_properties.c.sample_hash == sample_hash)
        rows = self._connection.execute(statement.order_by(sample_properties.c.rate, note_event.c.sounded_note))
        return tuple(_row_to_note_usage(row) for row in rows)

    def note_usage_for_every_sample(self) -> Iterator[tuple[str, SampleNoteUsage]]:
        """The same rate-and-note usage for the whole catalog, one group at a time.

        Streamed in server-side batches: the catalog holds tens of millions of note events reaching
        hundreds of thousands of distinct groups, and a caller folding them into a rate per sample
        can do so as they arrive. This is a minute of database work, which belongs to a pipeline
        pass rather than to a served request.
        """
        statement = self._usage_statement().add_columns(sample_properties.c.sample_hash)
        rows = self._connection.execute(statement.execution_options(yield_per=_USAGE_BATCH_SIZE))
        for row in rows:
            yield row.sample_hash, _row_to_note_usage(row)

    def _usage_statement(self) -> Select[tuple[int, int, int]]:
        """The rate-and-note grouping both usage readings share, before either narrows it."""
        # pylint: disable-next=not-callable
        event_count = func.count().label("event_count")
        return (
            select(sample_properties.c.rate, note_event.c.sounded_note, event_count)
            .select_from(
                note_event.join(
                    sample_properties,
                    (sample_properties.c.module_id == note_event.c.module_id)
                    & (sample_properties.c.instrument_index == note_event.c.instrument_index)
                    & (sample_properties.c.sample_slot == note_event.c.sample_slot),
                )
            )
            .where(note_event.c.sounded_note.is_not(None))
            .group_by(sample_properties.c.sample_hash, sample_properties.c.rate, note_event.c.sounded_note)
        )

    def note_statistics_for_every_sample(self) -> dict[str, SampleNoteStatistics]:
        """How every sample the note events reach is played, in one pass over the whole catalog.

        Read together with a descriptor, these say whether an embedding puts samples used the same
        way near one another, over the part of the catalog note events cover -- which is most of it,
        and far more than any keyword label reaches. One aggregate query serves the whole catalog,
        since naming a hash per sample would pass Postgres's parameter ceiling many times over.
        """
        # pylint: disable-next=not-callable
        strike_count = func.count().label("strike_count")
        # pylint: disable-next=not-callable
        distinct_pitch_count = func.count(func.distinct(note_event.c.sounded_note)).label("distinct_pitch_count")
        statement = (
            select(
                sample_properties.c.sample_hash,
                distinct_pitch_count,
                func.min(note_event.c.sounded_note).label("lowest_note"),
                func.max(note_event.c.sounded_note).label("highest_note"),
                strike_count,
            )
            .select_from(
                note_event.join(
                    sample_properties,
                    (sample_properties.c.module_id == note_event.c.module_id)
                    & (sample_properties.c.instrument_index == note_event.c.instrument_index)
                    & (sample_properties.c.sample_slot == note_event.c.sample_slot),
                )
            )
            .where(note_event.c.sounded_note.is_not(None))
            .group_by(sample_properties.c.sample_hash)
        )
        rows = self._connection.execute(statement).fetchall()
        return {
            row.sample_hash: SampleNoteStatistics(
                sample_hash=row.sample_hash,
                distinct_pitch_count=row.distinct_pitch_count,
                lowest_note=Note(row.lowest_note),
                highest_note=Note(row.highest_note),
                strike_count=row.strike_count,
            )
            for row in rows
        }


def _row_to_note_usage(row: Row[Any]) -> SampleNoteUsage:
    """Reconstruct a SampleNoteUsage from a grouped row, addressed by its own column names."""
    return SampleNoteUsage(reference_rate_hz=row.rate, sounded_note=Note(row.sounded_note), event_count=row.event_count)


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
