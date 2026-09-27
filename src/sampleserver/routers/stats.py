from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import Connection

from samplecore.models.stats import LibraryStats
from samplecore.storage.stats import compute_library_stats
from sampleserver.dependencies import READ_CONNECTION

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("")
def get_stats(connection: Connection = READ_CONNECTION) -> LibraryStats:
    """A snapshot of the catalog's overall size and composition."""
    return compute_library_stats(connection)
