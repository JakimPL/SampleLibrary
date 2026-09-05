from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends, HTTPException

from samplecore.models.relation import SampleRelation
from samplecore.models.sample import Sample
from samplecore.models.sample_properties import TrackerSampleProperties
from samplecore.storage.repositories.relation import DuckDBSampleRelationRepository
from samplecore.storage.repositories.sample import DuckDBSampleRepository
from samplecore.storage.repositories.sample_properties import DuckDBSamplePropertiesRepository
from sampleserver.dependencies import get_connection

router = APIRouter(prefix="/samples", tags=["samples"])


class SampleDetail(Sample):
    """A sample together with every occurrence, across the whole catalog, that references it."""

    occurrences: tuple[TrackerSampleProperties, ...]


@router.get("/{sample_hash}")
def get_sample(sample_hash: str, connection: duckdb.DuckDBPyConnection = Depends(get_connection)) -> SampleDetail:
    """One sample's own fields plus every module occurrence that references it.

    Raises:
        HTTPException: 404 when no sample is catalogued under this hash.
    """
    sample = DuckDBSampleRepository(connection).get(sample_hash)
    if sample is None:
        raise HTTPException(status_code=404, detail=f"no sample catalogued with hash {sample_hash!r}")

    occurrences = DuckDBSamplePropertiesRepository(connection).list_for_sample(sample_hash)
    return SampleDetail(**sample.model_dump(), occurrences=occurrences)


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
