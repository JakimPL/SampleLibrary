from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Connection

from samplecore.anchoring import anchored_annotations
from samplecore.labeling.labels import SampleLabel
from samplecore.labeling.vocabulary import LabelVocabulary, first_use_ranks
from samplecore.models.annotation import AnnotationDecisions, AnnotationSource
from samplecore.models.base import FROZEN
from samplecore.models.scalars import SampleHash
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_annotation import (
    PostgresSampleAnnotationRepository,
)
from sampleserver.dependencies import get_connection, get_curation_connection
from sampleserver.equivalence import equivalence_class_members

router = APIRouter(prefix="/curation", tags=["curation"])


class AnnotationRequest(AnnotationDecisions):
    """The whole state a person wants a sample, or its whole group, to carry from here on.

    Every decision is sent on every write, so what a person left empty is what the sample ends up
    saying nothing about. An emptied label arrives as ``null``: blank text is malformed rather than
    a way to clear one, which keeps a slip of the keyboard from silently discarding a decision.
    """

    scope: AnnotationSource


class TagSummary(BaseModel):
    """One tag a person has used: its path, how many samples carry it, and a rank that stays with it.

    The count includes every sample labeled with a specification below the tag. The rank is the
    order the tag was first used in, which is what a viewer hangs a lasting color on: it keeps its
    value as the vocabulary grows, where a place in a most-used ordering changes with every label.
    """

    model_config = FROZEN

    path: tuple[str, ...]
    sample_count: int
    rank: int


class AnnotationWritten(BaseModel):
    """What every reached sample now says, so a caller updates exactly the rows that changed."""

    model_config = FROZEN

    annotation: AnnotationDecisions | None
    sample_hashes: tuple[SampleHash, ...]


@router.put("/annotations/{sample_hash}")
def set_annotation(
    sample_hash: str,
    request: AnnotationRequest,
    connection: Connection = Depends(get_connection),
    curation_connection: Connection = Depends(get_curation_connection),
) -> AnnotationWritten:
    """Record what a person decided about this sample, optionally across its near-duplicates.

    The whole state arrives at once and replaces whatever the sample said before. A state recording
    nothing removes the annotation, which is how a person takes a decision back.

    A scope of ``equivalence_class`` reaches every sample the detector groups with this one, which
    is the same group the listing collapses under one row, and each member is written as its own row
    so the group boundary moving later leaves those decisions intact. A sample with no detected
    relation forms a group of one, so both scopes behave identically for it. A member the catalog
    holds no occurrence for has nowhere to anchor, so its annotation is removed rather than left
    saying something the group no longer says.

    The catalog is read through the read-only connection and only the annotation is written, which
    keeps the one write this application performs to the schema it owns.

    Raises:
        HTTPException: 404 when no sample is cataloged under this hash.
    """
    _require_cataloged(connection, sample_hash)
    decisions = AnnotationDecisions(label=request.label, rating=request.rating, favorite=request.favorite)
    hashes = _scoped_hashes(connection, sample_hash, scope=request.scope)
    written = (
        anchored_annotations(
            connection,
            sample_hashes=hashes,
            decisions=decisions,
            source=request.scope,
            annotated_at=datetime.now(UTC),
        )
        if decisions.records_a_decision
        else ()
    )

    anchored = {annotation.sample_hash for annotation in written}
    repository = PostgresSampleAnnotationRepository(curation_connection)
    with start_batch(curation_connection):
        repository.delete_many(tuple(item for item in hashes if item not in anchored))
        repository.replace_many(written)

    return AnnotationWritten(
        annotation=decisions if decisions.records_a_decision else None,
        sample_hashes=hashes,
    )


@router.get("/annotations/vocabulary")
def get_label_vocabulary(curation_connection: Connection = Depends(get_curation_connection)) -> tuple[str, ...]:
    """Every label already in use, most-used first, for offering a person their own wording back."""
    return PostgresSampleAnnotationRepository(curation_connection).vocabulary()


@router.get("/annotations/tags")
def get_label_tags(curation_connection: Connection = Depends(get_curation_connection)) -> tuple[TagSummary, ...]:
    """Every tag in use, read out of the labels as paths, most used first.

    Where `get_label_vocabulary` offers whole wordings back to the person typing one, this reads the
    tags inside them -- ``HI-HAT: CLOSED, LO-FI`` names three -- for a viewer that colors or filters
    by what the labels say. The tree comes whole; a viewer takes the depth it wants.
    """
    annotations = PostgresSampleAnnotationRepository(curation_connection).list_all()
    vocabulary = LabelVocabulary.from_labels(
        SampleLabel.parse(annotation.label) for annotation in annotations if annotation.label is not None
    )
    ranks = first_use_ranks(annotations)
    return tuple(
        TagSummary(path=usage.path, sample_count=usage.sample_count, rank=ranks[usage.path])
        for usage in vocabulary.usages
    )


def _require_cataloged(connection: Connection, sample_hash: str) -> None:
    if PostgresSampleRepository(connection).get(sample_hash) is None:
        raise HTTPException(status_code=404, detail=f"no sample cataloged with hash {sample_hash!r}")


def _scoped_hashes(connection: Connection, sample_hash: str, *, scope: AnnotationSource) -> tuple[str, ...]:
    match scope:
        case AnnotationSource.SAMPLE:
            return (sample_hash,)
        case AnnotationSource.EQUIVALENCE_CLASS:
            return equivalence_class_members(connection, sample_hash)
