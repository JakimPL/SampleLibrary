from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Connection

from samplecore.models.base import FROZEN
from samplecore.models.module import Module
from samplecore.models.sample import Sample
from samplecore.models.sample_properties import TrackerSampleProperties
from samplecore.models.scalars import Count
from samplecore.models.thumbnail import SampleThumbnail
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository
from samplecore.storage.repositories.thumbnail import PostgresSampleThumbnailRepository, peaks_from_thumbnail
from samplecore.waveform import WaveformPeak
from sampleserver.dependencies import get_connection
from sampleserver.pagination import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page

router = APIRouter(prefix="/modules", tags=["modules"])


class ModuleOccurrenceSample(Sample):
    """The resolved Sample content one module occurrence points at, alongside its cached thumbnail.

    ``size_bytes`` re-exposes ``Sample.stored_bytes`` under its own name, the same rename
    ``SampleSummary`` already uses: a Pydantic field cannot share a name with an inherited plain
    property without the property silently winning on attribute access.
    """

    size_bytes: Count
    thumbnail: tuple[WaveformPeak, ...] | None


class ModuleOccurrenceDetail(BaseModel):
    """One sample occurrence a module declares, together with the Sample content it points at."""

    model_config = FROZEN

    properties: TrackerSampleProperties
    sample: ModuleOccurrenceSample


class ModuleDetail(Module):
    """A module together with every sample occurrence it declares."""

    occurrences: tuple[ModuleOccurrenceDetail, ...]


@router.get("")
def list_modules(
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)] = DEFAULT_PAGE_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
    tracker: TrackerFormat | None = None,
    connection: Connection = Depends(get_connection),
) -> Page[Module]:
    """A page of catalogued modules, optionally filtered by tracker format."""
    repository = PostgresModuleRepository(connection)
    items = repository.list_page(limit=limit, offset=offset, tracker=tracker)
    total = repository.count(tracker=tracker)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{module_hash}")
def get_module(module_hash: str, connection: Connection = Depends(get_connection)) -> ModuleDetail:
    """One module's own fields plus every sample occurrence it declares.

    Raises:
        HTTPException: 404 when no module is catalogued under this hash.
    """
    module = PostgresModuleRepository(connection).get(module_hash)
    if module is None:
        raise HTTPException(status_code=404, detail=f"no module catalogued with hash {module_hash!r}")

    properties = PostgresSamplePropertiesRepository(connection).list_for_module(module_hash)
    samples_by_hash = _samples_by_hash(connection, properties)
    occurrences = tuple(
        ModuleOccurrenceDetail(properties=item, sample=samples_by_hash[item.sample_hash]) for item in properties
    )
    return ModuleDetail(**module.model_dump(), occurrences=occurrences)


def _samples_by_hash(
    connection: Connection, properties: tuple[TrackerSampleProperties, ...]
) -> dict[str, ModuleOccurrenceSample]:
    hashes = sorted({item.sample_hash for item in properties})
    samples = PostgresSampleRepository(connection).get_many(hashes)
    thumbnails_by_hash = PostgresSampleThumbnailRepository(connection).get_many(hashes)

    samples_by_hash: dict[str, ModuleOccurrenceSample] = {}
    for sample_hash in hashes:
        sample = samples.get(sample_hash)
        if sample is None:
            raise ValueError(f"module occurrence references sample {sample_hash!r}, which is not catalogued")

        samples_by_hash[sample_hash] = _occurrence_sample(sample, thumbnails_by_hash.get(sample_hash))

    return samples_by_hash


def _occurrence_sample(sample: Sample, thumbnail: SampleThumbnail | None) -> ModuleOccurrenceSample:
    return ModuleOccurrenceSample(
        **sample.model_dump(), size_bytes=sample.stored_bytes, thumbnail=peaks_from_thumbnail(thumbnail)
    )
