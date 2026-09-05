from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Protocol

import duckdb

from samplecore.models.relation import RelationReview, RelationType, SampleRelation

_SELECT_COLUMNS = (
    "id, subject_hash, reference_hash, relation_type, method, confidence, evidence, "
    "detected_at, reviewed_confirmed, reviewed_at, reviewed_by"
)


class SampleRelationRepository(Protocol):
    """Persistence for detected equivalence-class links between Samples."""

    def next_id(self) -> int: ...

    def upsert(self, relation: SampleRelation) -> None: ...

    def review(self, relation_id: int, review: RelationReview) -> None: ...

    def list_all(self) -> tuple[SampleRelation, ...]: ...


class DuckDBSampleRelationRepository:
    """A SampleRelationRepository backed by the catalog's ``sample_relation`` table.

    ``evidence`` is stored as a JSON-encoded string rather than the native ``JSON`` column type,
    so its round trip through this repository never depends on how a particular DuckDB version
    chooses to represent that type in the Python API.
    """

    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._connection = connection

    def next_id(self) -> int:
        row = self._connection.execute("SELECT nextval('sample_relation_id_seq')").fetchone()
        assert row is not None
        return int(row[0])

    def upsert(self, relation: SampleRelation) -> None:
        review = relation.review
        self._connection.execute(
            """
            INSERT INTO sample_relation (
                id, subject_hash, reference_hash, relation_type, method, confidence, evidence,
                detected_at, reviewed_confirmed, reviewed_at, reviewed_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (subject_hash, reference_hash, relation_type, method) DO UPDATE SET
                confidence = EXCLUDED.confidence,
                evidence = EXCLUDED.evidence,
                detected_at = EXCLUDED.detected_at
            """,
            [
                relation.id,
                relation.subject_hash,
                relation.reference_hash,
                relation.relation_type.value,
                relation.method,
                relation.confidence,
                json.dumps(relation.evidence),
                relation.detected_at,
                review.confirmed if review is not None else None,
                review.reviewed_at if review is not None else None,
                review.reviewed_by if review is not None else None,
            ],
        )

    def review(self, relation_id: int, review: RelationReview) -> None:
        self._connection.execute(
            "UPDATE sample_relation SET reviewed_confirmed = ?, reviewed_at = ?, reviewed_by = ? WHERE id = ?",
            [review.confirmed, review.reviewed_at, review.reviewed_by, relation_id],
        )

    def get(self, relation_id: int) -> SampleRelation | None:
        row = self._connection.execute(
            f"SELECT {_SELECT_COLUMNS} FROM sample_relation WHERE id = ?", [relation_id]
        ).fetchone()
        return _row_to_relation(row) if row is not None else None

    def list_all(self) -> tuple[SampleRelation, ...]:
        rows = self._connection.execute(f"SELECT {_SELECT_COLUMNS} FROM sample_relation").fetchall()
        return tuple(_row_to_relation(row) for row in rows)


def _row_to_relation(row: tuple[Any, ...]) -> SampleRelation:
    """Reconstruct a SampleRelation from a raw DuckDB row, an untyped boundary whose column order is fixed above."""
    (
        id_,
        subject_hash,
        reference_hash,
        relation_type,
        method,
        confidence,
        evidence,
        detected_at,
        reviewed_confirmed,
        reviewed_at,
        reviewed_by,
    ) = row
    review = _review_from_row(reviewed_confirmed, reviewed_at, reviewed_by)
    return SampleRelation(
        id=id_,
        subject_hash=subject_hash,
        reference_hash=reference_hash,
        relation_type=RelationType(relation_type),
        method=method,
        confidence=confidence,
        evidence=json.loads(evidence),
        detected_at=detected_at,
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
