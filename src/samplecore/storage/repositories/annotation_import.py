from __future__ import annotations

from typing import Protocol

from sqlalchemy import Connection, select
from sqlalchemy.dialects.postgresql import insert as upsert

from samplecore.models.annotation import AnnotationImport
from samplecore.storage.curation import annotation_import


class AnnotationImportRepository(Protocol):
    """Persistence for the record of every labels file read into the catalog."""

    def record(self, imported: AnnotationImport) -> None: ...

    def get(self, file_sha256: str) -> AnnotationImport | None: ...


class PostgresAnnotationImportRepository:
    """An AnnotationImportRepository backed by the curation schema's ``annotation_import`` table."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def record(self, imported: AnnotationImport) -> None:
        """Record a file read into the catalog, a file read before taking the later time and count."""
        statement = upsert(annotation_import).values(
            file_sha256=imported.file_sha256,
            annotation_count=imported.annotation_count,
            imported_at=imported.imported_at,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[annotation_import.c.file_sha256],
            set_={
                "annotation_count": statement.excluded.annotation_count,
                "imported_at": statement.excluded.imported_at,
            },
        )
        self._connection.execute(statement)

    def get(self, file_sha256: str) -> AnnotationImport | None:
        """The import of the file with this digest, or nothing when no such file was read in."""
        row = self._connection.execute(
            select(annotation_import).where(annotation_import.c.file_sha256 == file_sha256)
        ).fetchone()
        if row is None:
            return None
        return AnnotationImport(
            file_sha256=row.file_sha256, annotation_count=row.annotation_count, imported_at=row.imported_at
        )
