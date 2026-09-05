from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import Connection

from samplecore.models.stats import LibraryStats
from samplecore.storage.stats import compute_library_stats
from sampleserver.dependencies import get_connection

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("")
def get_stats(connection: Connection = Depends(get_connection)) -> LibraryStats:
    """A snapshot of the catalog's overall size and composition."""
    return compute_library_stats(connection)
