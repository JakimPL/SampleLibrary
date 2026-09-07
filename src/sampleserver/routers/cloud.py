from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import Connection

from samplecore.categorization import classify_sample_category
from samplecore.models.category import SampleCategory
from samplecore.models.cloud import ModuleCloudCoordinate, SampleCloudCoordinate
from samplecore.storage.repositories.cloud import (
    PostgresCloudCoordinateRepository,
    PostgresModuleCloudCoordinateRepository,
)
from samplecore.storage.repositories.sample import PostgresSampleRepository
from sampleserver.dependencies import get_connection

router = APIRouter(prefix="/cloud", tags=["cloud"])


class SampleCloudPoint(SampleCloudCoordinate):
    """A SampleCloudCoordinate together with its sample's derived category, for cloud coloring.

    ``category`` is computed the same way `SampleSummary.category` is -- at read time, from the
    sample's own occurrence names -- rather than stored alongside the coordinate itself.
    """

    category: SampleCategory


@router.get("")
def get_cloud(connection: Connection = Depends(get_connection)) -> tuple[SampleCloudPoint, ...]:
    """Every sample's position in the library's 2D embedding space, as of the latest embedding run."""
    coordinates = PostgresCloudCoordinateRepository(connection).list_all()
    names_by_hash, _ = PostgresSampleRepository(connection).names_and_rates_by_hash(
        [coordinate.sample_hash for coordinate in coordinates]
    )
    return tuple(
        SampleCloudPoint(
            sample_hash=coordinate.sample_hash,
            x=coordinate.x,
            y=coordinate.y,
            computed_at=coordinate.computed_at,
            category=classify_sample_category(names_by_hash.get(coordinate.sample_hash, ())),
        )
        for coordinate in coordinates
    )


@router.get("/modules")
def get_module_cloud(connection: Connection = Depends(get_connection)) -> tuple[ModuleCloudCoordinate, ...]:
    """Every module's placeholder position in the library's 2D embedding space.

    Placeholder until a spectral-distance-based per-module embedding replaces it -- see
    `samplecloud.placeholder_modules`.
    """
    return PostgresModuleCloudCoordinateRepository(connection).list_all()
