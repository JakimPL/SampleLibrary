from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from sqlalchemy import Connection, Row, select

from samplecore.models.experiment import SampleFeatureVector
from samplecore.storage.database import bulk_insert, sample_feature_vector


class SampleFeatureVectorRepository(Protocol):
    """Persistence for each Sample's raw extractor output, scoped to one Experiment."""

    def insert_many(self, vectors: Sequence[SampleFeatureVector]) -> None: ...

    def list_for_experiment(self, experiment_id: int) -> tuple[SampleFeatureVector, ...]: ...


class PostgresSampleFeatureVectorRepository:
    """A SampleFeatureVectorRepository backed by the catalog's ``sample_feature_vector`` table.

    ``insert_many`` never needs conflict resolution: a resumed experiment's caller only ever passes
    hashes ``list_for_experiment`` has not already returned for that same experiment, so a
    (experiment_id, sample_hash) pair this table already holds is never re-inserted.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def insert_many(self, vectors: Sequence[SampleFeatureVector]) -> None:
        if not vectors:
            return

        bulk_insert(
            self._connection,
            sample_feature_vector,
            ["experiment_id", "sample_hash", "vector", "computed_at"],
            ((vector.experiment_id, vector.sample_hash, list(vector.vector), vector.computed_at) for vector in vectors),
        )

    def list_for_experiment(self, experiment_id: int) -> tuple[SampleFeatureVector, ...]:
        statement = select(sample_feature_vector).where(sample_feature_vector.c.experiment_id == experiment_id)
        rows = self._connection.execute(statement).fetchall()
        return tuple(_row_to_feature_vector(row) for row in rows)


def _row_to_feature_vector(row: Row[Any]) -> SampleFeatureVector:
    """Reconstruct a SampleFeatureVector from a Core row, addressed by its own column names."""
    return SampleFeatureVector(
        experiment_id=row.experiment_id,
        sample_hash=row.sample_hash,
        vector=tuple(row.vector),
        computed_at=row.computed_at,
    )
