from __future__ import annotations

from typing import Protocol

from sqlalchemy import Connection, Row, select
from sqlalchemy.dialects.postgresql import insert

from samplecore.models.cloud import SampleCloudCoordinate
from samplecore.storage.database import sample_cloud_coordinates


class CloudCoordinateRepository(Protocol):
    """Persistence for where each Sample sits in the library's 2D embedding space."""

    def upsert(self, coordinate: SampleCloudCoordinate) -> None: ...

    def list_all(self) -> tuple[SampleCloudCoordinate, ...]: ...


class DuckDBCloudCoordinateRepository:
    """A CloudCoordinateRepository backed by the catalog's ``sample_cloud_coordinates`` table.

    ``upsert`` replaces a sample's coordinate outright: unlike a Sample's own hash-determined
    fields, a position comes from a whole embedding run's fit and is expected to change between
    runs, so the latest run's value always wins.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def upsert(self, coordinate: SampleCloudCoordinate) -> None:
        statement = insert(sample_cloud_coordinates).values(
            sample_hash=coordinate.sample_hash, x=coordinate.x, y=coordinate.y, computed_at=coordinate.computed_at
        )
        statement = statement.on_conflict_do_update(
            index_elements=[sample_cloud_coordinates.c.sample_hash],
            set_={
                "x": statement.excluded.x,
                "y": statement.excluded.y,
                "computed_at": statement.excluded.computed_at,
            },
        )
        self._connection.execute(statement)

    def list_all(self) -> tuple[SampleCloudCoordinate, ...]:
        rows = self._connection.execute(select(sample_cloud_coordinates)).fetchall()
        return tuple(_row_to_coordinate(row) for row in rows)


def _row_to_coordinate(row: Row[tuple[str, float, float, object]]) -> SampleCloudCoordinate:
    """Reconstruct a SampleCloudCoordinate from a Core row, addressed by its own column names."""
    return SampleCloudCoordinate(sample_hash=row.sample_hash, x=row.x, y=row.y, computed_at=row.computed_at)
