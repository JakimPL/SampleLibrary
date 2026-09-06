from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy import Connection, Row, delete, select
from sqlalchemy.dialects.postgresql import insert as upsert

from samplecore.models.cloud import ModuleCloudCoordinate, SampleCloudCoordinate
from samplecore.storage.database import bulk_insert_csv, module_cloud_coordinates, sample_cloud_coordinates


class CloudCoordinateRepository(Protocol):
    """Persistence for where each Sample sits in the library's 2D embedding space."""

    def upsert(self, coordinate: SampleCloudCoordinate) -> None: ...

    def replace_all(self, coordinates: Sequence[SampleCloudCoordinate]) -> None: ...

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
        statement = upsert(sample_cloud_coordinates).values(
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

    def replace_all(self, coordinates: Sequence[SampleCloudCoordinate]) -> None:
        """Replace every persisted coordinate with exactly the given set, in one bulk operation.

        A full-recompute writer like ``reduce_and_persist_coordinates`` never needs conflict
        resolution against a previous value -- every run replaces the whole table -- so clearing it
        first and bulk-loading fresh (see ``bulk_insert_csv``) stands in for a conflict-checked
        upsert per row, the difference between seconds and hours at this catalog's scale.
        """
        self._connection.execute(delete(sample_cloud_coordinates))
        if not coordinates:
            return
        bulk_insert_csv(
            self._connection,
            sample_cloud_coordinates,
            ["sample_hash", "x", "y", "computed_at"],
            (
                (coordinate.sample_hash, coordinate.x, coordinate.y, coordinate.computed_at)
                for coordinate in coordinates
            ),
        )

    def list_all(self) -> tuple[SampleCloudCoordinate, ...]:
        rows = self._connection.execute(select(sample_cloud_coordinates)).fetchall()
        return tuple(_row_to_coordinate(row) for row in rows)


def _row_to_coordinate(row: Row[tuple[str, float, float, object]]) -> SampleCloudCoordinate:
    """Reconstruct a SampleCloudCoordinate from a Core row, addressed by its own column names."""
    return SampleCloudCoordinate(sample_hash=row.sample_hash, x=row.x, y=row.y, computed_at=row.computed_at)


class ModuleCloudCoordinateRepository(Protocol):
    """Persistence for where each Module sits in the library's 2D embedding space."""

    def upsert(self, coordinate: ModuleCloudCoordinate) -> None: ...

    def replace_all(self, coordinates: Sequence[ModuleCloudCoordinate]) -> None: ...

    def list_all(self) -> tuple[ModuleCloudCoordinate, ...]: ...


class DuckDBModuleCloudCoordinateRepository:
    """A ModuleCloudCoordinateRepository backed by the catalog's ``module_cloud_coordinates`` table.

    Mirrors DuckDBCloudCoordinateRepository's replace-outright upsert: a position comes from a
    whole embedding run's fit, placeholder or genuine, so the latest run's value always wins.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def upsert(self, coordinate: ModuleCloudCoordinate) -> None:
        statement = upsert(module_cloud_coordinates).values(
            module_hash=coordinate.module_hash, x=coordinate.x, y=coordinate.y, computed_at=coordinate.computed_at
        )
        statement = statement.on_conflict_do_update(
            index_elements=[module_cloud_coordinates.c.module_hash],
            set_={
                "x": statement.excluded.x,
                "y": statement.excluded.y,
                "computed_at": statement.excluded.computed_at,
            },
        )
        self._connection.execute(statement)

    def replace_all(self, coordinates: Sequence[ModuleCloudCoordinate]) -> None:
        """Replace every persisted coordinate with exactly the given set, in one bulk operation.

        Mirrors ``DuckDBCloudCoordinateRepository.replace_all`` -- a full-recompute writer like
        ``place_and_persist_coordinates`` replaces the whole table every run, so a bulk clear and
        bulk-load (see ``bulk_insert_csv``) stands in for a conflict-checked upsert per row.
        """
        self._connection.execute(delete(module_cloud_coordinates))
        if not coordinates:
            return
        bulk_insert_csv(
            self._connection,
            module_cloud_coordinates,
            ["module_hash", "x", "y", "computed_at"],
            (
                (coordinate.module_hash, coordinate.x, coordinate.y, coordinate.computed_at)
                for coordinate in coordinates
            ),
        )

    def list_all(self) -> tuple[ModuleCloudCoordinate, ...]:
        rows = self._connection.execute(select(module_cloud_coordinates)).fetchall()
        return tuple(_row_to_module_coordinate(row) for row in rows)


def _row_to_module_coordinate(row: Row[tuple[str, float, float, object]]) -> ModuleCloudCoordinate:
    """Reconstruct a ModuleCloudCoordinate from a Core row, addressed by its own column names."""
    return ModuleCloudCoordinate(module_hash=row.module_hash, x=row.x, y=row.y, computed_at=row.computed_at)
