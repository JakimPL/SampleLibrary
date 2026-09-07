from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import Connection
from trackmod.schema.scalars import Rate

from samplecore.categorization import classify_sample_category
from samplecore.models.category import SampleCategory
from samplecore.models.cloud import ModuleCloudCoordinate, SampleCloudCoordinate
from samplecore.naming import choose_dominant_rate
from samplecore.storage.repositories.cloud import (
    PostgresCloudCoordinateRepository,
    PostgresModuleCloudCoordinateRepository,
)
from samplecore.storage.repositories.sample import PostgresSampleRepository
from sampleserver.dependencies import get_connection

router = APIRouter(prefix="/cloud", tags=["cloud"])


class SampleCloudPoint(SampleCloudCoordinate):
    """A SampleCloudCoordinate together with what a viewer needs to colour and hear the point.

    ``category`` is computed the same way `SampleSummary.category` is -- at read time, from the
    sample's own occurrence names together with the names of the instruments reaching it -- rather
    than stored alongside the coordinate itself. ``dominant_rate_hz`` travels with the point so
    clicking one plays it at a real tracker rate; it is ``None`` for a sample with no occurrences.
    """

    category: SampleCategory
    dominant_rate_hz: Rate | None


@router.get("")
def get_cloud(connection: Connection = Depends(get_connection)) -> tuple[SampleCloudPoint, ...]:
    """Every sample's position in the library's 2D embedding space, as of the latest embedding run."""
    coordinates = PostgresCloudCoordinateRepository(connection).list_all()
    repository = PostgresSampleRepository(connection)
    hashes = [coordinate.sample_hash for coordinate in coordinates]
    names_by_hash, rates_by_hash = repository.names_and_rates_by_hash(hashes)
    instrument_names_by_hash = repository.instrument_names_by_hash(hashes)
    return tuple(
        SampleCloudPoint(
            sample_hash=coordinate.sample_hash,
            x=coordinate.x,
            y=coordinate.y,
            computed_at=coordinate.computed_at,
            category=classify_sample_category(
                names_by_hash.get(coordinate.sample_hash, ()) + instrument_names_by_hash.get(coordinate.sample_hash, ())
            ),
            dominant_rate_hz=choose_dominant_rate(rates_by_hash.get(coordinate.sample_hash, ())),
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
