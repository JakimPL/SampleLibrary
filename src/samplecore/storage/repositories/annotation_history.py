from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Final

from pydantic import BaseModel
from sqlalchemy import Connection, func, select, text

from samplecore.models.annotation import AnnotationDecisions, HistoryOperation, SampleAnnotation
from samplecore.models.base import FROZEN
from samplecore.models.scalars import SampleHash
from samplecore.storage.curation import ANNOTATION_HISTORY_TABLE, CURATION_SCHEMA, annotation_history
from samplecore.storage.repositories.sample_annotation import row_to_sample_annotation

# The newest entry of each sample up to the moment, read back into the annotation table's own row
# type, so the history's JSON comes out with the columns and types the table gives it.
_ANNOTATIONS_AS_OF: Final = text(f"""
    SELECT (jsonb_populate_record(NULL::{CURATION_SCHEMA}.sample_annotation, latest.current)).*
    FROM (
        SELECT DISTINCT ON (sample_hash) operation, current
        FROM {CURATION_SCHEMA}.{ANNOTATION_HISTORY_TABLE}
        WHERE recorded_at <= :moment
        ORDER BY sample_hash, id DESC
    ) AS latest
    WHERE latest.operation <> '{HistoryOperation.DELETE.value}'
    """)


class AnnotationChange(BaseModel):
    """One entry of the label history: what a sample's decisions were before and after, when, and by which role."""

    model_config = FROZEN

    entry_id: int
    sample_hash: SampleHash
    operation: HistoryOperation
    recorded_at: datetime
    role: str
    previous: AnnotationDecisions | None
    current: AnnotationDecisions | None


class PostgresAnnotationHistoryRepository:
    """The label history in ``curation.annotation_history``, which a database trigger writes and this reads."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def started_at(self) -> datetime | None:
        """The moment the first entry was recorded, or None while the history holds none."""
        # pylint: disable-next=not-callable
        started: datetime | None = self._connection.execute(select(func.min(annotation_history.c.recorded_at))).scalar()
        return started

    def annotations_as_of(self, moment: datetime) -> tuple[SampleAnnotation, ...]:
        """Every annotation as it stood at ``moment``, whole, anchors included."""
        rows = self._connection.execute(_ANNOTATIONS_AS_OF, {"moment": moment}).fetchall()
        return tuple(row_to_sample_annotation(row) for row in rows)

    def changes(self, *, sample_hash: str | None, since: datetime | None, limit: int) -> tuple[AnnotationChange, ...]:
        """The newest ``limit`` entries, oldest first, of one sample or of all, from ``since`` on."""
        statement = select(annotation_history).order_by(annotation_history.c.id.desc()).limit(limit)
        if sample_hash is not None:
            statement = statement.where(annotation_history.c.sample_hash == sample_hash)
        if since is not None:
            statement = statement.where(annotation_history.c.recorded_at >= since)
        rows = self._connection.execute(statement).fetchall()
        return tuple(
            AnnotationChange(
                entry_id=row.id,
                sample_hash=row.sample_hash,
                operation=HistoryOperation(row.operation),
                recorded_at=row.recorded_at,
                role=row.role,
                previous=_decisions(row.previous),
                current=_decisions(row.current),
            )
            for row in reversed(rows)
        )


def _decisions(stored_row: Mapping[str, Any] | None) -> AnnotationDecisions | None:
    if stored_row is None:
        return None
    return AnnotationDecisions(label=stored_row["label"], rating=stored_row["rating"], favorite=stored_row["favorite"])
