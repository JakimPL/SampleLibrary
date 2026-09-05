from __future__ import annotations

from pathlib import Path
from typing import Annotated

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from samplecore.models.base import FROZEN
from samplecore.models.module import Module
from samplecore.models.relation import SampleRelation
from samplecore.models.sample import Sample, SampleSummary
from samplecore.models.sample_properties import TrackerSampleProperties
from samplecore.models.scalars import Count, ModuleHash
from samplecore.models.tracker import TrackerFormat
from samplecore.naming import choose_dominant_name
from samplecore.storage import audio_store
from samplecore.storage.repositories.module import DuckDBModuleRepository
from samplecore.storage.repositories.relation import DuckDBSampleRelationRepository
from samplecore.storage.repositories.sample import DuckDBSampleRepository
from samplecore.storage.repositories.sample_properties import DuckDBSamplePropertiesRepository
from samplecore.waveform import DEFAULT_WAVEFORM_BUCKET_COUNT, WaveformPeak, compute_waveform_peaks
from sampleserver.dependencies import get_connection, get_library_root
from sampleserver.pagination import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page

router = APIRouter(prefix="/samples", tags=["samples"])


class SampleOccurrenceModule(BaseModel):
    """The module context a sample occurrence belongs to, resolved for display alongside it."""

    model_config = FROZEN

    hash: ModuleHash
    filename: str
    title: str
    tracker: TrackerFormat


class SampleOccurrenceDetail(BaseModel):
    """One module occurrence of a sample, together with the module it belongs to."""

    model_config = FROZEN

    properties: TrackerSampleProperties
    module: SampleOccurrenceModule


class SampleDetail(Sample):
    """A sample together with every module occurrence that references it."""

    occurrences: tuple[SampleOccurrenceDetail, ...]
    size_bytes: Count
    display_name: str
    duration_seconds: float


@router.get("")
def list_samples(
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)] = DEFAULT_PAGE_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
    connection: duckdb.DuckDBPyConnection = Depends(get_connection),
) -> Page[SampleSummary]:
    """A page of catalogued samples, ranked by how many module occurrences reference each one.

    Ranks by sample identity: one row per exact content hash. Ranking by equivalence class --
    grouping near-duplicate variants into one row -- is a planned future mode, not available yet.
    """
    repository = DuckDBSampleRepository(connection)
    items = repository.list_page(limit=limit, offset=offset)
    total = repository.count()
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{sample_hash}")
def get_sample(sample_hash: str, connection: duckdb.DuckDBPyConnection = Depends(get_connection)) -> SampleDetail:
    """One sample's own fields plus every module occurrence that references it.

    Raises:
        HTTPException: 404 when no sample is catalogued under this hash.
    """
    sample = DuckDBSampleRepository(connection).get(sample_hash)
    if sample is None:
        raise HTTPException(status_code=404, detail=f"no sample catalogued with hash {sample_hash!r}")

    properties = DuckDBSamplePropertiesRepository(connection).list_for_sample(sample_hash)
    modules_by_hash = _modules_by_hash(connection, properties)
    occurrences = tuple(
        SampleOccurrenceDetail(properties=item, module=_occurrence_module(modules_by_hash[item.occurrence.module_hash]))
        for item in properties
    )
    return SampleDetail(
        hash=sample.hash,
        depth=sample.depth,
        channels=sample.channels,
        frames=sample.frames,
        occurrences=occurrences,
        size_bytes=sample.stored_bytes,
        display_name=choose_dominant_name(item.name for item in properties),
        duration_seconds=sample.frames / audio_store.NOMINAL_WAV_RATE,
    )


@router.get("/{sample_hash}/audio")
def get_sample_audio(
    sample_hash: str,
    connection: duckdb.DuckDBPyConnection = Depends(get_connection),
    library_root: Path = Depends(get_library_root),
) -> FileResponse:
    """The sample's own canonical audio, as stored in the content-addressable store.

    Raises:
        HTTPException: 404 when no sample is catalogued under this hash.
    """
    if DuckDBSampleRepository(connection).get(sample_hash) is None:
        raise HTTPException(status_code=404, detail=f"no sample catalogued with hash {sample_hash!r}")

    return FileResponse(audio_store.object_path(library_root, sample_hash), media_type="audio/wav")


@router.get("/{sample_hash}/waveform")
def get_sample_waveform(
    sample_hash: str,
    connection: duckdb.DuckDBPyConnection = Depends(get_connection),
    library_root: Path = Depends(get_library_root),
) -> tuple[WaveformPeak, ...]:
    """A compact amplitude-envelope preview of the sample's own waveform.

    Raises:
        HTTPException: 404 when no sample is catalogued under this hash.
    """
    sample = DuckDBSampleRepository(connection).get(sample_hash)
    if sample is None:
        raise HTTPException(status_code=404, detail=f"no sample catalogued with hash {sample_hash!r}")

    pcm = audio_store.read(library_root, sample).pcm
    return compute_waveform_peaks(pcm, bucket_count=DEFAULT_WAVEFORM_BUCKET_COUNT)


@router.get("/{sample_hash}/relations")
def get_sample_relations(
    sample_hash: str, connection: duckdb.DuckDBPyConnection = Depends(get_connection)
) -> tuple[SampleRelation, ...]:
    """Every equivalence-class link this sample participates in, on either side of the pair.

    Raises:
        HTTPException: 404 when no sample is catalogued under this hash.
    """
    if DuckDBSampleRepository(connection).get(sample_hash) is None:
        raise HTTPException(status_code=404, detail=f"no sample catalogued with hash {sample_hash!r}")

    return DuckDBSampleRelationRepository(connection).list_for_sample(sample_hash)


def _modules_by_hash(
    connection: duckdb.DuckDBPyConnection, properties: tuple[TrackerSampleProperties, ...]
) -> dict[str, Module]:
    repository = DuckDBModuleRepository(connection)
    modules_by_hash: dict[str, Module] = {}
    for item in properties:
        module_hash = item.occurrence.module_hash
        if module_hash in modules_by_hash:
            continue

        module = repository.get(module_hash)
        if module is None:
            raise ValueError(f"sample occurrence references module {module_hash!r}, which is not catalogued")

        modules_by_hash[module_hash] = module

    return modules_by_hash


def _occurrence_module(module: Module) -> SampleOccurrenceModule:
    return SampleOccurrenceModule(
        hash=module.hash, filename=module.filename, title=module.title, tracker=module.tracker
    )
