from __future__ import annotations

from typing import Any, Protocol

import duckdb

from samplecore.models.cloud import SampleCloudCoordinate


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

    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._connection = connection

    def upsert(self, coordinate: SampleCloudCoordinate) -> None:
        self._connection.execute(
            """
            INSERT INTO sample_cloud_coordinates (sample_hash, x, y, computed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (sample_hash) DO UPDATE SET
                x = EXCLUDED.x,
                y = EXCLUDED.y,
                computed_at = EXCLUDED.computed_at
            """,
            [coordinate.sample_hash, coordinate.x, coordinate.y, coordinate.computed_at],
        )

    def list_all(self) -> tuple[SampleCloudCoordinate, ...]:
        rows = self._connection.execute(
            "SELECT sample_hash, x, y, computed_at FROM sample_cloud_coordinates"
        ).fetchall()
        return tuple(_row_to_coordinate(row) for row in rows)


def _row_to_coordinate(row: tuple[Any, ...]) -> SampleCloudCoordinate:
    """Reconstruct a SampleCloudCoordinate from a raw DuckDB row, an untyped boundary whose column order is fixed above."""
    sample_hash, x, y, computed_at = row
    return SampleCloudCoordinate(sample_hash=sample_hash, x=x, y=y, computed_at=computed_at)
