from __future__ import annotations

from typing import Protocol

from sqlalchemy import Connection, select

from samplecore.models.note_extraction import ModuleNoteExtraction
from samplecore.storage.database import module_note_extraction


class ModuleNoteExtractionRepository(Protocol):
    """Persistence for which modules have had their patterns read for the notes they play."""

    def mark(self, extraction: ModuleNoteExtraction) -> None: ...

    def extracted_module_ids(self) -> frozenset[int]: ...

    def delete_for_module(self, module_id: int) -> None: ...


class PostgresModuleNoteExtractionRepository:
    """A ModuleNoteExtractionRepository backed by the catalog's ``module_note_extraction`` table.

    ``extracted_module_ids`` answers a whole pass in one query, because a resumed run asks the same
    question of every module it discovers and the catalog holds one row per module at most.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def mark(self, extraction: ModuleNoteExtraction) -> None:
        statement = module_note_extraction.insert().values(
            module_id=extraction.module_id, extracted_at=extraction.extracted_at
        )
        self._connection.execute(statement)

    def extracted_module_ids(self) -> frozenset[int]:
        rows = self._connection.execute(select(module_note_extraction.c.module_id)).fetchall()
        return frozenset(row.module_id for row in rows)

    def delete_for_module(self, module_id: int) -> None:
        self._connection.execute(module_note_extraction.delete().where(module_note_extraction.c.module_id == module_id))
