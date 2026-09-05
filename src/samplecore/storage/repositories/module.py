from __future__ import annotations

from typing import Any, Protocol, TypeVar

from sqlalchemy import Connection, Row, Select, func, select

from samplecore.models.module import Module
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.database import module, module_id_sequence

_SelectT = TypeVar("_SelectT", bound=Select[Any])


class ModuleRepository(Protocol):
    """Persistence for the Module catalog: one row per ingested tracker module file."""

    def get(self, hash_: str) -> Module | None: ...

    def next_id(self) -> int: ...

    def insert(self, module_: Module) -> None: ...

    def list_page(self, *, limit: int, offset: int, tracker: TrackerFormat | None = None) -> tuple[Module, ...]: ...

    def count(self, *, tracker: TrackerFormat | None = None) -> int: ...


class DuckDBModuleRepository:
    """A ModuleRepository backed by the catalog's ``module`` table.

    A module's ``id`` is assigned before construction, via ``next_id``, rather than left to the
    table's own sequence default: the domain model requires an id up front, so the caller must
    already hold one by the time it builds a complete ``Module`` to insert.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get(self, hash_: str) -> Module | None:
        row = self._connection.execute(select(module).where(module.c.hash == hash_)).fetchone()
        return _row_to_module(row) if row is not None else None

    def next_id(self) -> int:
        return self._connection.execute(select(module_id_sequence.next_value())).scalar_one()

    def insert(self, module_: Module) -> None:
        self._connection.execute(
            module.insert().values(
                id=module_.id,
                hash=module_.hash,
                filename=module_.filename,
                tracker=module_.tracker.value,
                title=module_.title,
                channel_count=module_.channel_count,
                pattern_count=module_.pattern_count,
                instrument_count=module_.instrument_count,
                sample_count=module_.sample_count,
                file_size=module_.file_size,
                ingested_at=module_.ingested_at,
            )
        )

    def list_page(self, *, limit: int, offset: int, tracker: TrackerFormat | None = None) -> tuple[Module, ...]:
        statement = select(module).order_by(module.c.id).limit(limit).offset(offset)
        statement = _with_tracker_filter(statement, tracker)
        rows = self._connection.execute(statement).fetchall()
        return tuple(_row_to_module(row) for row in rows)

    def count(self, *, tracker: TrackerFormat | None = None) -> int:
        # func.count() is SQLAlchemy's dynamically-generated SQL COUNT(*), invisible to pylint's static analysis.
        # pylint: disable-next=not-callable
        statement = select(func.count()).select_from(module)
        statement = _with_tracker_filter(statement, tracker)
        return self._connection.execute(statement).scalar_one()


def _with_tracker_filter(statement: _SelectT, tracker: TrackerFormat | None) -> _SelectT:
    if tracker is None:
        return statement

    return statement.where(module.c.tracker == tracker.value)


def _row_to_module(row: Row[Any]) -> Module:
    """Reconstruct a Module from a Core row, addressed by its own column names."""
    return Module(
        hash=row.hash,
        id=row.id,
        filename=row.filename,
        tracker=TrackerFormat(row.tracker),
        title=row.title,
        channel_count=row.channel_count,
        pattern_count=row.pattern_count,
        instrument_count=row.instrument_count,
        sample_count=row.sample_count,
        file_size=row.file_size,
        ingested_at=row.ingested_at,
    )
