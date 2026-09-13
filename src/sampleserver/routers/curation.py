from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Final, Self

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as RoutePath
from fastapi import Response
from pydantic import BaseModel, ConfigDict, Strict, model_validator
from sqlalchemy import Connection

from samplecore.anchoring import anchors_by_hash
from samplecore.labeling.labels import LabelPath, SampleLabel
from samplecore.labeling.vocabulary import LabelVocabulary
from samplecore.models.annotation import (
    AnnotationChanges,
    AnnotationDecision,
    AnnotationDecisions,
    AnnotationSource,
    LabelText,
)
from samplecore.models.base import FROZEN
from samplecore.models.scalars import SAMPLE_HASH_PATTERN, Rating, SampleHash
from samplecore.storage.annotation_writes import AnnotationWrite, write_annotation_changes
from samplecore.storage.curation import claim_annotation_writes, read_tag_ranks
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_annotation import (
    PostgresSampleAnnotationRepository,
)
from sampleserver.dependencies import get_connection, get_curation_connection
from sampleserver.equivalence import equivalence_class_members

router = APIRouter(prefix="/curation", tags=["curation"])

SampleHashPath = Annotated[str, RoutePath(pattern=SAMPLE_HASH_PATTERN)]
DECISION_FIELDS: Final[frozenset[str]] = frozenset(decision.value for decision in AnnotationDecision)


class AnnotationChangeRequest(BaseModel):
    """The decisions one gesture changes about a sample, or about its whole group.

    A decision left out of the request stays as the sample holds it; a decision sent as ``null``
    is cleared, and a favorite is cleared by sending ``false``. Values arrive as the JSON types they
    are, so a rating is a number and a favorite a boolean. An emptied label arrives as ``null``: text
    naming no tag is malformed rather than a way to clear one, which keeps a slip of the keyboard
    from silently discarding a decision.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: AnnotationSource
    label: Annotated[LabelText, Strict()] | None = None
    rating: Annotated[Rating, Strict()] | None = None
    favorite: Annotated[bool, Strict()] = False

    @model_validator(mode="after")
    def _names_a_decision(self) -> Self:
        if not self.model_fields_set & DECISION_FIELDS:
            raise ValueError(f"a change names at least one of {', '.join(sorted(DECISION_FIELDS))}")
        return self

    @property
    def changes(self) -> AnnotationChanges:
        """The request as the change it makes, naming exactly the decisions the request sent."""
        return AnnotationChanges(
            values=AnnotationDecisions(label=self.label, rating=self.rating, favorite=self.favorite),
            changed=frozenset(AnnotationDecision(name) for name in self.model_fields_set & DECISION_FIELDS),
        )


class TagSummary(BaseModel):
    """One tag a person has used: its path, how many samples carry it, and a rank that stays with it.

    The count includes every sample labeled with a specification below the tag. The rank follows
    the order tags were first used in and stays with its tag for good, which is what a viewer hangs
    a lasting color on.
    """

    model_config = FROZEN

    path: tuple[str, ...]
    sample_count: int
    rank: int


class WrittenAnnotation(BaseModel):
    """What one reached sample says once a write has landed, ``null`` for a sample saying nothing."""

    model_config = FROZEN

    sample_hash: SampleHash
    annotation: AnnotationDecisions | None


class AnnotationsWritten(BaseModel):
    """What every reached sample now says, so a caller updates exactly the rows that changed.

    ``skipped`` names the group members the change would have given a first decision to while the
    catalog holds nothing to anchor them to; they go on saying nothing.
    """

    model_config = FROZEN

    samples: tuple[WrittenAnnotation, ...]
    skipped: tuple[SampleHash, ...]


@router.patch("/annotations/{sample_hash}")
def change_annotation(
    sample_hash: SampleHashPath,
    request: AnnotationChangeRequest,
    connection: Connection = Depends(get_connection),
    curation_connection: Connection = Depends(get_curation_connection),
) -> AnnotationsWritten:
    """Change what a person decided about this sample, optionally across its near-duplicates.

    Every reached sample keeps the decisions the request leaves out, so a star given to a group
    changes the members' ratings alone. A scope of ``equivalence_class`` reaches every sample the
    detector groups with this one, the same group the listing collapses under one row, and each
    member is written as its own row so the group boundary moving later leaves those decisions
    intact. A sample left recording nothing has its annotation removed, which is how a person takes
    a decision back.

    The catalog is read through the read-only connection and only the curation schema is written,
    which keeps the one write this application performs to the schema it owns.

    Raises:
        HTTPException: 404 when no sample is cataloged under this hash and none is annotated.
    """
    sample_hashes = _reached_hashes(connection, curation_connection, sample_hash, scope=request.scope)
    plan = write_annotation_changes(
        curation_connection,
        AnnotationWrite(
            sample_hashes=sample_hashes,
            changes=request.changes,
            source=request.scope,
            annotated_at=datetime.now(UTC),
        ),
        anchors=anchors_by_hash(connection, sample_hashes),
    )
    return AnnotationsWritten(
        samples=tuple(
            WrittenAnnotation(sample_hash=item.sample_hash, annotation=item.decisions) for item in plan.written
        ),
        skipped=plan.skipped,
    )


@router.delete("/annotations/{sample_hash}", status_code=204)
def remove_annotation(
    sample_hash: SampleHashPath, curation_connection: Connection = Depends(get_curation_connection)
) -> Response:
    """Take back everything a person decided about one sample, whether or not the catalog still holds it.

    An annotation whose sample has left the catalog for good, and that relinking cannot place, is
    removed through here.

    Raises:
        HTTPException: 404 when no annotation is held for this hash.
    """
    with start_batch(curation_connection):
        claim_annotation_writes(curation_connection)
        removed = PostgresSampleAnnotationRepository(curation_connection).delete_many((sample_hash,))
    if not removed:
        raise HTTPException(status_code=404, detail=f"no annotation held for hash {sample_hash!r}")
    return Response(status_code=204)


@router.get("/annotations/vocabulary")
def get_label_vocabulary(connection: Connection = Depends(get_connection)) -> tuple[str, ...]:
    """Every label already in use, most-used first, for offering a person their own wording back."""
    return PostgresSampleAnnotationRepository(connection).vocabulary()


@router.get("/annotations/tags")
def get_label_tags(connection: Connection = Depends(get_connection)) -> tuple[TagSummary, ...]:
    """Every tag in use, read out of the labels as paths, most used first.

    Where `get_label_vocabulary` offers whole wordings back to the person typing one, this reads the
    tags inside them -- ``HI-HAT: CLOSED, LO-FI`` names three -- for a viewer that colors or filters
    by what the labels say. The tree comes whole; a viewer takes the depth it wants.
    """
    annotations = PostgresSampleAnnotationRepository(connection).list_all()
    vocabulary = LabelVocabulary.from_labels(
        SampleLabel.parse(annotation.label) for annotation in annotations if annotation.label is not None
    )
    ranks = _ranks_for(tuple(usage.path for usage in vocabulary.usages), read_tag_ranks(connection))
    return tuple(
        TagSummary(path=usage.path, sample_count=usage.sample_count, rank=ranks[usage.path])
        for usage in vocabulary.usages
    )


def _ranks_for(paths: tuple[LabelPath, ...], stored: dict[LabelPath, int]) -> dict[LabelPath, int]:
    """Each tag's stored rank, and for a tag written before ranks were kept, a rank after all of them by name."""
    unranked = sorted(path for path in paths if path not in stored)
    after_stored = max(stored.values(), default=-1) + 1
    return stored | {path: after_stored + offset for offset, path in enumerate(unranked)}


def _reached_hashes(
    connection: Connection, curation_connection: Connection, sample_hash: str, *, scope: AnnotationSource
) -> tuple[str, ...]:
    """The samples one write reaches: the sample alone, or its whole equivalence class.

    A sample the catalog no longer holds keeps its annotation reachable on its own, so a person can
    still change or clear what they said about it.

    Raises:
        HTTPException: 404 when no sample is cataloged under this hash and none is annotated.
    """
    if PostgresSampleRepository(connection).get(sample_hash) is None:
        if PostgresSampleAnnotationRepository(curation_connection).get(sample_hash) is None:
            raise HTTPException(status_code=404, detail=f"no sample cataloged or annotated with hash {sample_hash!r}")
        return (sample_hash,)

    match scope:
        case AnnotationSource.SAMPLE:
            return (sample_hash,)
        case AnnotationSource.EQUIVALENCE_CLASS:
            return equivalence_class_members(connection, sample_hash)
