from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import Connection, Row, or_, select
from sqlalchemy.dialects.postgresql import insert

from samplecore.models.relation import RelationReview, RelationType, SampleRelation
from samplecore.storage.database import sample_relation, sample_relation_id_sequence


class SampleRelationRepository(Protocol):
    """Persistence for detected equivalence-class links between Samples."""

    def next_id(self) -> int: ...

    def upsert(self, relation: SampleRelation) -> None: ...

    def review(self, relation_id: int, review: RelationReview) -> None: ...

    def get(self, relation_id: int) -> SampleRelation | None: ...

    def list_all(self) -> tuple[SampleRelation, ...]: ...

    def list_for_sample(self, sample_hash: str) -> tuple[SampleRelation, ...]: ...


class PostgresSampleRelationRepository:
    """A SampleRelationRepository backed by the catalog's ``sample_relation`` table.

    ``evidence`` is stored as a JSON-encoded string rather than the native ``JSON``/``JSONB`` column
    type, so its round trip through this repository never depends on a particular database's own
    JSON representation.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def next_id(self) -> int:
        return self._connection.execute(select(sample_relation_id_sequence.next_value())).scalar_one()

    def upsert(self, relation: SampleRelation) -> None:
        review = relation.review
        statement = insert(sample_relation).values(
            id=relation.id,
            subject_hash=relation.subject_hash,
            reference_hash=relation.reference_hash,
            relation_type=relation.relation_type.value,
            method=relation.method,
            confidence=relation.confidence,
            evidence=json.dumps(relation.evidence),
            detected_at=relation.detected_at,
            reviewed_confirmed=review.confirmed if review is not None else None,
            reviewed_at=review.reviewed_at if review is not None else None,
            reviewed_by=review.reviewed_by if review is not None else None,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[
                sample_relation.c.subject_hash,
                sample_relation.c.reference_hash,
                sample_relation.c.relation_type,
                sample_relation.c.method,
            ],
            set_={
                "confidence": statement.excluded.confidence,
                "evidence": statement.excluded.evidence,
                "detected_at": statement.excluded.detected_at,
            },
        )
        self._connection.execute(statement)

    def review(self, relation_id: int, review: RelationReview) -> None:
        self._connection.execute(
            sample_relation.update()
            .where(sample_relation.c.id == relation_id)
            .values(reviewed_confirmed=review.confirmed, reviewed_at=review.reviewed_at, reviewed_by=review.reviewed_by)
        )

    def get(self, relation_id: int) -> SampleRelation | None:
        row = self._connection.execute(select(sample_relation).where(sample_relation.c.id == relation_id)).fetchone()
        return _row_to_relation(row) if row is not None else None

    def list_all(self) -> tuple[SampleRelation, ...]:
        rows = self._connection.execute(select(sample_relation)).fetchall()
        return tuple(_row_to_relation(row) for row in rows)

    def list_for_sample(self, sample_hash: str) -> tuple[SampleRelation, ...]:
        statement = select(sample_relation).where(
            or_(sample_relation.c.subject_hash == sample_hash, sample_relation.c.reference_hash == sample_hash)
        )
        rows = self._connection.execute(statement).fetchall()
        return tuple(_row_to_relation(row) for row in rows)


def _row_to_relation(row: Row[Any]) -> SampleRelation:
    """Reconstruct a SampleRelation from a Core row, addressed by its own column names."""
    review = _review_from_row(row.reviewed_confirmed, row.reviewed_at, row.reviewed_by)
    return SampleRelation(
        id=row.id,
        subject_hash=row.subject_hash,
        reference_hash=row.reference_hash,
        relation_type=RelationType(row.relation_type),
        method=row.method,
        confidence=row.confidence,
        evidence=json.loads(row.evidence),
        detected_at=row.detected_at,
        review=review,
    )


def _review_from_row(
    confirmed: bool | None, reviewed_at: datetime | None, reviewed_by: str | None
) -> RelationReview | None:
    if confirmed is None:
        return None
    if reviewed_at is None or reviewed_by is None:
        raise ValueError("a stored review must have confirmed, reviewed_at, and reviewed_by set together")

    return RelationReview(confirmed=confirmed, reviewed_at=reviewed_at, reviewed_by=reviewed_by)
