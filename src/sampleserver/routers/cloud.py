from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import Connection

from samplecore.models.cloud import ModuleCloudCoordinate, SampleCloudCoordinate
from samplecore.storage.repositories.cloud import DuckDBCloudCoordinateRepository, DuckDBModuleCloudCoordinateRepository
from sampleserver.dependencies import get_connection

router = APIRouter(prefix="/cloud", tags=["cloud"])


@router.get("")
def get_cloud(connection: Connection = Depends(get_connection)) -> tuple[SampleCloudCoordinate, ...]:
    """Every sample's position in the library's 2D embedding space, as of the latest embedding run."""
    return DuckDBCloudCoordinateRepository(connection).list_all()


@router.get("/modules")
def get_module_cloud(connection: Connection = Depends(get_connection)) -> tuple[ModuleCloudCoordinate, ...]:
    """Every module's placeholder position in the library's 2D embedding space.

    Placeholder until a spectral-distance-based per-module embedding replaces it -- see
    `samplecloud.placeholder_modules`.
    """
    return DuckDBModuleCloudCoordinateRepository(connection).list_all()
