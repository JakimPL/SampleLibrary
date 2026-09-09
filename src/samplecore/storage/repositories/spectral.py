from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol

import numpy as np
from sqlalchemy import Connection, Row, delete, func, select
from sqlalchemy.dialects.postgresql import insert as upsert

from samplecore.models.spectral import SampleSpectralFeature
from samplecore.spectral_distance import SpectralVectors
from samplecore.storage.database import bulk_insert, sample_spectral_feature


class SampleSpectralFeatureRepository(Protocol):
    """Persistence for each Sample's standardized spectral feature vector, as of one embedding run."""

    def upsert(self, feature: SampleSpectralFeature) -> None: ...

    def replace_all(self, features: Sequence[SampleSpectralFeature]) -> None: ...

    def get(self, sample_hash: str) -> SampleSpectralFeature | None: ...

    def list_all(self) -> tuple[SampleSpectralFeature, ...]: ...

    def vectors(self) -> SpectralVectors: ...

    def revision(self) -> tuple[int, datetime | None]: ...


class PostgresSampleSpectralFeatureRepository:
    """A SampleSpectralFeatureRepository backed by the catalog's ``sample_spectral_feature`` table.

    ``vector`` is stored as a JSON-encoded string rather than the native ``JSON``/``JSONB`` column
    type, mirroring ``PostgresSampleRelationRepository``'s own reasoning: its round trip then never
    depends on a particular database's own JSON representation. ``upsert``
    replaces a sample's vector outright, mirroring ``PostgresCloudCoordinateRepository``'s own
    replace-outright semantics -- both come from the same embedding run's fit.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def upsert(self, feature: SampleSpectralFeature) -> None:
        statement = upsert(sample_spectral_feature).values(
            sample_hash=feature.sample_hash,
            vector=json.dumps(feature.vector),
            computed_at=feature.computed_at,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[sample_spectral_feature.c.sample_hash],
            set_={"vector": statement.excluded.vector, "computed_at": statement.excluded.computed_at},
        )
        self._connection.execute(statement)

    def replace_all(self, features: Sequence[SampleSpectralFeature]) -> None:
        """Replace every persisted vector with exactly the given set, in one bulk operation.

        A full-recompute writer like ``reduce_and_persist_coordinates`` never needs conflict
        resolution against a previous value -- every run replaces the whole table -- so clearing it
        first and bulk-loading fresh (see ``bulk_insert``) stands in for a conflict-checked
        upsert per row, the difference between seconds and hours at this catalog's scale.
        """
        self._connection.execute(delete(sample_spectral_feature))
        if not features:
            return
        bulk_insert(
            self._connection,
            sample_spectral_feature,
            ["sample_hash", "vector", "computed_at"],
            ((feature.sample_hash, json.dumps(feature.vector), feature.computed_at) for feature in features),
        )

    def get(self, sample_hash: str) -> SampleSpectralFeature | None:
        row = self._connection.execute(
            select(sample_spectral_feature).where(sample_spectral_feature.c.sample_hash == sample_hash)
        ).fetchone()
        return _row_to_feature(row) if row is not None else None

    def list_all(self) -> tuple[SampleSpectralFeature, ...]:
        rows = self._connection.execute(select(sample_spectral_feature)).fetchall()
        return tuple(_row_to_feature(row) for row in rows)

    def vectors(self) -> SpectralVectors:
        """Every persisted vector as one matrix, for a search measuring the whole catalog at once.

        Reads the stored text straight into the matrix, since a nearest-neighbor search wants the
        numbers rather than a model per sample: building a hundred thousand of those costs more than
        the query that fetched them.
        """
        rows = self._connection.execute(
            select(sample_spectral_feature.c.sample_hash, sample_spectral_feature.c.vector)
        ).fetchall()
        matrix = np.array([json.loads(row.vector) for row in rows], dtype=np.float64)
        return SpectralVectors(hashes=tuple(row.sample_hash for row in rows), matrix=matrix)

    def revision(self) -> tuple[int, datetime | None]:
        """What the vectors on file amount to right now: how many there are, and when last written.

        An embedding run replaces every row and stamps them all, so a reader holding a parsed copy
        of the vectors can tell in one cheap query whether that copy still describes the catalog.
        """
        row = self._connection.execute(
            select(
                # pylint: disable-next=not-callable
                func.count(),
                func.max(sample_spectral_feature.c.computed_at),
            ).select_from(sample_spectral_feature)
        ).one()
        count: int = row[0]
        computed_at: datetime | None = row[1]
        return count, computed_at


def _row_to_feature(row: Row[Any]) -> SampleSpectralFeature:
    """Reconstruct a SampleSpectralFeature from a Core row, addressed by its own column names."""
    return SampleSpectralFeature(
        sample_hash=row.sample_hash, vector=tuple(json.loads(row.vector)), computed_at=row.computed_at
    )
