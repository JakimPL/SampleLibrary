from __future__ import annotations

import json
from typing import Any, Protocol

from sqlalchemy import Connection, Row, select
from sqlalchemy.dialects.postgresql import insert

from samplecore.models.spectral import SampleSpectralFeature
from samplecore.storage.database import sample_spectral_feature


class SampleSpectralFeatureRepository(Protocol):
    """Persistence for each Sample's standardized spectral feature vector, as of one embedding run."""

    def upsert(self, feature: SampleSpectralFeature) -> None: ...

    def get(self, sample_hash: str) -> SampleSpectralFeature | None: ...

    def list_all(self) -> tuple[SampleSpectralFeature, ...]: ...


class DuckDBSampleSpectralFeatureRepository:
    """A SampleSpectralFeatureRepository backed by the catalog's ``sample_spectral_feature`` table.

    ``vector`` is stored as a JSON-encoded string rather than the native ``JSON`` column type,
    mirroring ``DuckDBSampleRelationRepository``'s own reasoning: its round trip then never depends
    on how a particular DuckDB version chooses to represent that type in the Python API. ``upsert``
    replaces a sample's vector outright, mirroring ``DuckDBCloudCoordinateRepository``'s own
    replace-outright semantics -- both come from the same embedding run's fit.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def upsert(self, feature: SampleSpectralFeature) -> None:
        statement = insert(sample_spectral_feature).values(
            sample_hash=feature.sample_hash,
            vector=json.dumps(feature.vector),
            computed_at=feature.computed_at,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[sample_spectral_feature.c.sample_hash],
            set_={"vector": statement.excluded.vector, "computed_at": statement.excluded.computed_at},
        )
        self._connection.execute(statement)

    def get(self, sample_hash: str) -> SampleSpectralFeature | None:
        row = self._connection.execute(
            select(sample_spectral_feature).where(sample_spectral_feature.c.sample_hash == sample_hash)
        ).fetchone()
        return _row_to_feature(row) if row is not None else None

    def list_all(self) -> tuple[SampleSpectralFeature, ...]:
        rows = self._connection.execute(select(sample_spectral_feature)).fetchall()
        return tuple(_row_to_feature(row) for row in rows)


def _row_to_feature(row: Row[Any]) -> SampleSpectralFeature:
    """Reconstruct a SampleSpectralFeature from a Core row, addressed by its own column names."""
    return SampleSpectralFeature(
        sample_hash=row.sample_hash, vector=tuple(json.loads(row.vector)), computed_at=row.computed_at
    )
