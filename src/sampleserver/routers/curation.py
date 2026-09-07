from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Connection

from samplecore.labeling import anchored_labels
from samplecore.models.base import FROZEN
from samplecore.models.label import LabelSource, LabelText
from samplecore.models.scalars import SampleHash
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_label import PostgresSampleLabelRepository
from sampleserver.dependencies import get_connection, get_curation_connection
from sampleserver.equivalence import equivalence_class_members

router = APIRouter(prefix="/curation", tags=["curation"])


class LabelRequest(BaseModel):
    """What a person decided a sample is, and how far that decision should reach."""

    model_config = FROZEN

    label: LabelText
    scope: LabelSource


class LabelsWritten(BaseModel):
    """Which samples a labelling reached, so a caller updates exactly the rows that changed."""

    model_config = FROZEN

    label: str | None
    sample_hashes: tuple[SampleHash, ...]


@router.put("/labels/{sample_hash}")
def set_label(
    sample_hash: str,
    request: LabelRequest,
    connection: Connection = Depends(get_connection),
    curation_connection: Connection = Depends(get_curation_connection),
) -> LabelsWritten:
    """Record what a person decided this sample is, optionally across its near-duplicates.

    A scope of ``equivalence_class`` reaches every sample the detector groups with this one, which
    is the same group the listing collapses under one row, and each member is written as its own
    label so the group boundary moving later leaves those decisions intact. A sample with no
    detected relation forms a group of one, so both scopes behave identically for it.

    The catalog is read through the read-only connection and only the label is written, which keeps
    the one write this application performs to the schema it owns.

    Raises:
        HTTPException: 404 when no sample is catalogued under this hash.
    """
    _require_catalogued(connection, sample_hash)
    hashes = _scoped_hashes(connection, sample_hash, scope=request.scope)
    labels = anchored_labels(
        connection,
        sample_hashes=hashes,
        label=request.label,
        source=request.scope,
        labeled_at=datetime.now(UTC),
    )
    PostgresSampleLabelRepository(curation_connection).upsert_many(labels)
    curation_connection.commit()

    return LabelsWritten(label=request.label, sample_hashes=tuple(item.sample_hash for item in labels))


@router.delete("/labels/{sample_hash}")
def clear_label(
    sample_hash: str,
    scope: LabelSource = LabelSource.SAMPLE,
    connection: Connection = Depends(get_connection),
    curation_connection: Connection = Depends(get_curation_connection),
) -> LabelsWritten:
    """Take back a decision, over the same scope that could have made it.

    Raises:
        HTTPException: 404 when no sample is catalogued under this hash.
    """
    _require_catalogued(connection, sample_hash)
    hashes = _scoped_hashes(connection, sample_hash, scope=scope)
    PostgresSampleLabelRepository(curation_connection).delete_many(hashes)
    curation_connection.commit()

    return LabelsWritten(label=None, sample_hashes=hashes)


@router.get("/labels/vocabulary")
def get_label_vocabulary(curation_connection: Connection = Depends(get_curation_connection)) -> tuple[str, ...]:
    """Every label already in use, most-used first, for offering a person their own wording back."""
    return PostgresSampleLabelRepository(curation_connection).vocabulary()


def _require_catalogued(connection: Connection, sample_hash: str) -> None:
    if PostgresSampleRepository(connection).get(sample_hash) is None:
        raise HTTPException(status_code=404, detail=f"no sample catalogued with hash {sample_hash!r}")


def _scoped_hashes(connection: Connection, sample_hash: str, *, scope: LabelSource) -> tuple[str, ...]:
    match scope:
        case LabelSource.SAMPLE:
            return (sample_hash,)
        case LabelSource.EQUIVALENCE_CLASS:
            return equivalence_class_members(connection, sample_hash)
