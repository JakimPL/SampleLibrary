from __future__ import annotations

from typing import Any, Protocol

import duckdb

from samplecore.models.module import Module
from samplecore.models.tracker import TrackerFormat

_SELECT_COLUMNS = (
    "hash, id, filename, tracker, title, channel_count, pattern_count, "
    "instrument_count, sample_count, file_size, ingested_at"
)


class ModuleRepository(Protocol):
    """Persistence for the Module catalog: one row per ingested tracker module file."""

    def get(self, hash_: str) -> Module | None: ...

    def next_id(self) -> int: ...

    def insert(self, module: Module) -> None: ...

    def list_page(self, *, limit: int, offset: int, tracker: TrackerFormat | None = None) -> tuple[Module, ...]: ...

    def count(self, *, tracker: TrackerFormat | None = None) -> int: ...


class DuckDBModuleRepository:
    """A ModuleRepository backed by the catalog's ``module`` table.

    A module's ``id`` is assigned before construction, via ``next_id``, rather than left to the
    table's own sequence default: the domain model requires an id up front, so the caller must
    already hold one by the time it builds a complete ``Module`` to insert.
    """

    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._connection = connection

    def get(self, hash_: str) -> Module | None:
        row = self._connection.execute(f"SELECT {_SELECT_COLUMNS} FROM module WHERE hash = ?", [hash_]).fetchone()
        return _row_to_module(row) if row is not None else None

    def next_id(self) -> int:
        row = self._connection.execute("SELECT nextval('module_id_seq')").fetchone()
        assert row is not None
        return int(row[0])

    def insert(self, module: Module) -> None:
        self._connection.execute(
            """
            INSERT INTO module
                (id, hash, filename, tracker, title, channel_count, pattern_count,
                 instrument_count, sample_count, file_size, ingested_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                module.id,
                module.hash,
                module.filename,
                module.tracker.value,
                module.title,
                module.channel_count,
                module.pattern_count,
                module.instrument_count,
                module.sample_count,
                module.file_size,
                module.ingested_at,
            ],
        )

    def list_page(self, *, limit: int, offset: int, tracker: TrackerFormat | None = None) -> tuple[Module, ...]:
        clause, parameters = _tracker_filter(tracker)
        rows = self._connection.execute(
            f"SELECT {_SELECT_COLUMNS} FROM module{clause} ORDER BY id LIMIT ? OFFSET ?",
            [*parameters, limit, offset],
        ).fetchall()
        return tuple(_row_to_module(row) for row in rows)

    def count(self, *, tracker: TrackerFormat | None = None) -> int:
        clause, parameters = _tracker_filter(tracker)
        row = self._connection.execute(f"SELECT count(*) FROM module{clause}", parameters).fetchone()
        assert row is not None
        return int(row[0])


def _tracker_filter(tracker: TrackerFormat | None) -> tuple[str, list[str]]:
    if tracker is None:
        return "", []

    return " WHERE tracker = ?", [tracker.value]


def _row_to_module(row: tuple[Any, ...]) -> Module:
    """Reconstruct a Module from a raw DuckDB row, an untyped boundary whose column order is fixed above."""
    (
        hash_,
        id_,
        filename,
        tracker,
        title,
        channel_count,
        pattern_count,
        instrument_count,
        sample_count,
        file_size,
        ingested_at,
    ) = row
    return Module(
        hash=hash_,
        id=id_,
        filename=filename,
        tracker=TrackerFormat(tracker),
        title=title,
        channel_count=channel_count,
        pattern_count=pattern_count,
        instrument_count=instrument_count,
        sample_count=sample_count,
        file_size=file_size,
        ingested_at=ingested_at,
    )
