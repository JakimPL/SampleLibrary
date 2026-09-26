from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection

from samplecore.models.annotation import SampleAnnotation
from samplecore.storage.curation import claim_annotation_writes, register_tag_ranks
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.annotation_history import PostgresAnnotationHistoryRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository


class RestoreRefused(ValueError):
    """Raised when the label history cannot say how the labels stood at the moment asked for."""


@dataclass(frozen=True)
class RestorePlan:
    """What bringing the labels back to one moment changes: the annotations written, and the samples cleared."""

    moment: datetime
    upserts: tuple[SampleAnnotation, ...]
    removals: tuple[str, ...]
    unchanged: int


def plan_restore(
    *, moment: datetime, current: Mapping[str, SampleAnnotation], target: Mapping[str, SampleAnnotation]
) -> RestorePlan:
    """The writes turning the ``current`` annotations into the ``target`` ones, sample by sample."""
    upserts = tuple(
        target[sample_hash] for sample_hash in sorted(target) if current.get(sample_hash) != target[sample_hash]
    )
    removals = tuple(sorted(sample_hash for sample_hash in current if sample_hash not in target))
    return RestorePlan(moment=moment, upserts=upserts, removals=removals, unchanged=len(target) - len(upserts))


def restore_annotations(connection: Connection, *, moment: datetime, apply: bool) -> RestorePlan:
    """Bring every annotation back to how it stood at ``moment``, or only say what that would change.

    Whole rows come back from the history, anchors included, so a sample that has since left the
    catalog gets its annotation back too. The restore writes through the table like any other
    change, so the history records it, and restoring to the moment before it undoes it.

    Raises:
        RestoreRefused: the history begins after ``moment``, or holds nothing yet.
    """
    with start_batch(connection):
        claim_annotation_writes(connection)
        history = PostgresAnnotationHistoryRepository(connection)
        started_at = history.started_at()
        if started_at is None:
            raise RestoreRefused("the label history holds nothing yet")
        if moment < started_at:
            raise RestoreRefused(f"the label history begins at {started_at.astimezone():%Y-%m-%d %H:%M:%S}")
        annotations = PostgresSampleAnnotationRepository(connection)
        plan = plan_restore(
            moment=moment,
            current={annotation.sample_hash: annotation for annotation in annotations.list_all()},
            target={annotation.sample_hash: annotation for annotation in history.annotations_as_of(moment)},
        )
        if apply:
            annotations.delete_many(plan.removals)
            annotations.upsert_many(plan.upserts)
            restored_labels = sorted(plan.upserts, key=lambda annotation: annotation.annotated_at)
            register_tag_ranks(connection, (annotation.label for annotation in restored_labels if annotation.label))
    return plan
