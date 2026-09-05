from __future__ import annotations

from typing import Annotated

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query

from samplecore.models.module import Module
from samplecore.models.sample_properties import TrackerSampleProperties
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.repositories.module import DuckDBModuleRepository
from samplecore.storage.repositories.sample_properties import DuckDBSamplePropertiesRepository
from sampleserver.dependencies import get_connection
from sampleserver.pagination import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page

router = APIRouter(prefix="/modules", tags=["modules"])


class ModuleDetail(Module):
    """A module together with every sample occurrence it declares."""

    occurrences: tuple[TrackerSampleProperties, ...]


@router.get("")
def list_modules(
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)] = DEFAULT_PAGE_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
    tracker: TrackerFormat | None = None,
    connection: duckdb.DuckDBPyConnection = Depends(get_connection),
) -> Page[Module]:
    """A page of catalogued modules, optionally filtered by tracker format."""
    repository = DuckDBModuleRepository(connection)
    items = repository.list_page(limit=limit, offset=offset, tracker=tracker)
    total = repository.count(tracker=tracker)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{module_hash}")
def get_module(module_hash: str, connection: duckdb.DuckDBPyConnection = Depends(get_connection)) -> ModuleDetail:
    """One module's own fields plus every sample occurrence it declares.

    Raises:
        HTTPException: 404 when no module is catalogued under this hash.
    """
    module = DuckDBModuleRepository(connection).get(module_hash)
    if module is None:
        raise HTTPException(status_code=404, detail=f"no module catalogued with hash {module_hash!r}")

    occurrences = DuckDBSamplePropertiesRepository(connection).list_for_module(module_hash)
    return ModuleDetail(**module.model_dump(), occurrences=occurrences)
