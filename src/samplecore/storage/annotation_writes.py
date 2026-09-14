from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection

from samplecore.models.annotation import (
    NO_DECISIONS,
    AnnotationAnchor,
    AnnotationChanges,
    AnnotationDecisions,
    AnnotationSource,
    SampleAnnotation,
)
from samplecore.storage.curation import claim_annotation_writes, register_tag_ranks
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository


@dataclass(frozen=True)
class AnnotationWrite:
    """One gesture's change, the samples it reaches, and how and when it was made."""

    sample_hashes: tuple[str, ...]
    changes: AnnotationChanges
    source: AnnotationSource
    annotated_at: datetime


@dataclass(frozen=True)
class WrittenDecisions:
    """What one reached sample says once a write has landed, ``None`` for a sample saying nothing."""

    sample_hash: str
    decisions: AnnotationDecisions | None


@dataclass(frozen=True)
class AnnotationWritePlan:
    """The rows one change writes and removes, and what every reached sample says afterward.

    ``skipped`` names the samples a change would give their first decision to while nothing anchors
    them: the catalog holds neither a module occurrence nor a file of them, and no annotation of
    theirs carries an anchor, so they are left saying nothing.
    """

    upserts: tuple[SampleAnnotation, ...]
    removals: tuple[str, ...]
    written: tuple[WrittenDecisions, ...]
    skipped: tuple[str, ...]


def plan_annotation_write(
    write: AnnotationWrite, *, existing: Mapping[str, SampleAnnotation], anchors: Mapping[str, AnnotationAnchor]
) -> AnnotationWritePlan:
    """Merge one change into every reached sample's own annotation, deciding what to write and remove.

    Each sample keeps whatever the change leaves alone, so a star given to a group changes every
    member's rating and nothing else. A sample the change leaves exactly as it was is not written,
    which keeps the moment of its last decision where it stands. A sample left recording nothing has
    its row removed, which is how a person takes a decision back.
    """
    upserts: list[SampleAnnotation] = []
    removals: list[str] = []
    written: list[WrittenDecisions] = []
    skipped: list[str] = []
    for sample_hash in write.sample_hashes:
        stored = existing.get(sample_hash)
        current = stored.decisions if stored is not None else NO_DECISIONS
        merged = write.changes.applied_to(current)
        if merged == current:
            written.append(WrittenDecisions(sample_hash, current if current.records_a_decision else None))
        elif not merged.records_a_decision:
            removals.append(sample_hash)
            written.append(WrittenDecisions(sample_hash, None))
        else:
            anchor = anchors.get(sample_hash) or (stored.anchor if stored is not None else None)
            if anchor is None:
                skipped.append(sample_hash)
                continue
            upserts.append(_annotation(sample_hash, merged, anchor=anchor, write=write))
            written.append(WrittenDecisions(sample_hash, merged))

    return AnnotationWritePlan(
        upserts=tuple(upserts), removals=tuple(removals), written=tuple(written), skipped=tuple(skipped)
    )


def write_annotation_changes(
    curation_connection: Connection, write: AnnotationWrite, *, anchors: Mapping[str, AnnotationAnchor]
) -> AnnotationWritePlan:
    """Apply one change to every reached sample in one transaction, under the annotation write lock.

    What each sample holds is read after the lock is taken, so a change sent from a second tab a
    moment after the first merges into the state the first one committed.
    """
    repository = PostgresSampleAnnotationRepository(curation_connection)
    with start_batch(curation_connection):
        claim_annotation_writes(curation_connection)
        plan = plan_annotation_write(
            write, existing=repository.annotations_by_hash(list(write.sample_hashes)), anchors=anchors
        )
        repository.delete_many(plan.removals)
        repository.upsert_many(plan.upserts)
        register_tag_ranks(curation_connection, (item.label for item in plan.upserts if item.label is not None))

    return plan


def _annotation(
    sample_hash: str, decisions: AnnotationDecisions, *, anchor: AnnotationAnchor, write: AnnotationWrite
) -> SampleAnnotation:
    return SampleAnnotation(
        sample_hash=sample_hash,
        label=decisions.label,
        rating=decisions.rating,
        favorite=decisions.favorite,
        anchor=anchor,
        source=write.source,
        annotated_at=write.annotated_at,
    )
