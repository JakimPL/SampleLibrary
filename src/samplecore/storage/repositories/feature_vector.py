from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from sqlalchemy import Connection, Row, delete, select
from trackmod.schema.scalars import Rate

from samplecore.models.experiment import SampleFeatureVector
from samplecore.storage.database import HASH_CHUNK_SIZE, bulk_insert, chunks, sample_feature_vector


class SampleFeatureVectorRepository(Protocol):
    """Persistence for each Sample's raw extractor output, scoped to one Experiment."""

    def insert_many(self, vectors: Sequence[SampleFeatureVector]) -> None: ...

    def sample_hashes_for_experiment(self, experiment_id: int) -> frozenset[str]: ...

    def heard_rates_for_experiment(self, experiment_id: int) -> dict[str, Rate | None]: ...

    def delete_for_samples(self, experiment_id: int, sample_hashes: Sequence[str]) -> None: ...

    def vectors_in_hash_order(
        self, experiment_id: int, *, count: int, offset: int
    ) -> tuple[SampleFeatureVector, ...]: ...

    def list_for_experiment(self, experiment_id: int) -> tuple[SampleFeatureVector, ...]: ...


class PostgresSampleFeatureVectorRepository:
    """A SampleFeatureVectorRepository backed by the catalog's ``sample_feature_vector`` table.

    ``insert_many`` never needs conflict resolution: a resumed experiment's caller passes hashes the
    experiment holds no vector for, or first deletes the vectors it describes again
    (``delete_for_samples``), so a (experiment_id, sample_hash) pair this table already holds is
    never inserted a second time.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def insert_many(self, vectors: Sequence[SampleFeatureVector]) -> None:
        if not vectors:
            return

        bulk_insert(
            self._connection,
            sample_feature_vector,
            ["experiment_id", "sample_hash", "vector", "computed_at", "heard_rate"],
            (
                (vector.experiment_id, vector.sample_hash, list(vector.vector), vector.computed_at, vector.heard_rate)
                for vector in vectors
            ),
        )

    def sample_hashes_for_experiment(self, experiment_id: int) -> frozenset[str]:
        """The samples an experiment holds a vector for, read without the vectors themselves."""
        statement = select(sample_feature_vector.c.sample_hash).where(
            sample_feature_vector.c.experiment_id == experiment_id
        )
        return frozenset(str(row.sample_hash) for row in self._connection.execute(statement))

    def heard_rates_for_experiment(self, experiment_id: int) -> dict[str, Rate | None]:
        """The rate each of an experiment's samples was heard at when described, read without the vectors."""
        statement = select(sample_feature_vector.c.sample_hash, sample_feature_vector.c.heard_rate).where(
            sample_feature_vector.c.experiment_id == experiment_id
        )
        return {str(row.sample_hash): row.heard_rate for row in self._connection.execute(statement)}

    def delete_for_samples(self, experiment_id: int, sample_hashes: Sequence[str]) -> None:
        """Drop an experiment's vectors for these samples, ahead of describing them again."""
        for chunk in chunks(sample_hashes, HASH_CHUNK_SIZE):
            self._connection.execute(
                delete(sample_feature_vector)
                .where(sample_feature_vector.c.experiment_id == experiment_id)
                .where(sample_feature_vector.c.sample_hash.in_(chunk))
            )

    def vectors_in_hash_order(self, experiment_id: int, *, count: int, offset: int) -> tuple[SampleFeatureVector, ...]:
        """Up to ``count`` of an experiment's vectors in sample-hash order, past the first ``offset``, the same ones every call."""
        statement = (
            select(sample_feature_vector)
            .where(sample_feature_vector.c.experiment_id == experiment_id)
            .order_by(sample_feature_vector.c.sample_hash)
            .limit(count)
            .offset(offset)
        )
        return tuple(_row_to_feature_vector(row) for row in self._connection.execute(statement))

    def list_for_experiment(self, experiment_id: int) -> tuple[SampleFeatureVector, ...]:
        """One experiment's vectors in sample-hash order, so every reader of a row position means one sample."""
        statement = (
            select(sample_feature_vector)
            .where(sample_feature_vector.c.experiment_id == experiment_id)
            .order_by(sample_feature_vector.c.sample_hash)
        )
        rows = self._connection.execute(statement).fetchall()
        return tuple(_row_to_feature_vector(row) for row in rows)


def _row_to_feature_vector(row: Row[Any]) -> SampleFeatureVector:
    """Reconstruct a SampleFeatureVector from a Core row, addressed by its own column names."""
    return SampleFeatureVector(
        experiment_id=row.experiment_id,
        sample_hash=row.sample_hash,
        vector=tuple(row.vector),
        computed_at=row.computed_at,
        heard_rate=row.heard_rate,
    )
