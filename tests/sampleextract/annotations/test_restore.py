from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

import pytest
from sqlalchemy import Connection, func, select

from samplecore.models.annotation import AnnotationSource, SampleAnnotation, SampleFileAnchor
from samplecore.models.sample_file import SampleFileLocation
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository
from sampleextract.annotations.restore import RestoreRefused, plan_restore, restore_annotations

KICK_HASH: Final[str] = "a" * 64
SNARE_HASH: Final[str] = "b" * 64
UNCATALOGED_HASH: Final[str] = "c" * 64


def _annotation(sample_hash: str, *, label: str | None, rating: int | None = None) -> SampleAnnotation:
    return SampleAnnotation(
        sample_hash=sample_hash,
        label=label,
        rating=rating,
        favorite=False,
        anchor=SampleFileAnchor(
            location=SampleFileLocation(directory="/samples", relative_path=f"{sample_hash[:4]}.wav")
        ),
        source=AnnotationSource.SAMPLE,
        annotated_at=datetime(2026, 9, 26, 12, 0, tzinfo=UTC),
    )


class LabelTimeline:
    """A library whose labels change over several moments, each one marked so a restore can name it."""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection
        self.annotations = PostgresSampleAnnotationRepository(connection)

    def write(self, *annotations: SampleAnnotation) -> datetime:
        self.annotations.upsert_many(annotations)
        self.connection.commit()
        return self.mark()

    def clear(self, *sample_hashes: str) -> datetime:
        self.annotations.delete_many(sample_hashes)
        self.connection.commit()
        return self.mark()

    def mark(self) -> datetime:
        moment: datetime = self.connection.execute(select(func.clock_timestamp())).scalar_one()
        self.connection.commit()
        return moment

    def restore(self, moment: datetime) -> None:
        restore_annotations(self.connection, moment=moment, apply=True)
        self.connection.commit()

    def labels(self) -> dict[str, SampleAnnotation]:
        return {annotation.sample_hash: annotation for annotation in self.annotations.list_all()}


@pytest.fixture
def timeline(connection: Connection) -> LabelTimeline:
    return LabelTimeline(connection)


def test_the_labels_come_back_as_they_stood_at_each_moment(timeline: LabelTimeline) -> None:
    first = {KICK_HASH: _annotation(KICK_HASH, label="KICK")}
    after_first = timeline.write(*first.values())
    second = {
        KICK_HASH: _annotation(KICK_HASH, label="KICK: 909", rating=5),
        SNARE_HASH: _annotation(SNARE_HASH, label="SNARE"),
    }
    after_second = timeline.write(*second.values())
    timeline.clear(KICK_HASH, SNARE_HASH)

    timeline.restore(after_second)
    assert timeline.labels() == second

    timeline.restore(after_first)
    assert timeline.labels() == first


def test_a_restore_is_recorded_and_undone_by_restoring_to_the_moment_before_it(timeline: LabelTimeline) -> None:
    before_labeling = timeline.write(_annotation(SNARE_HASH, label="CLAP"))
    labeled = {SNARE_HASH: _annotation(SNARE_HASH, label="SNARE"), KICK_HASH: _annotation(KICK_HASH, label="KICK")}
    before_restore = timeline.write(*labeled.values())

    timeline.restore(before_labeling)
    assert timeline.labels() == {SNARE_HASH: _annotation(SNARE_HASH, label="CLAP")}

    timeline.restore(before_restore)
    assert timeline.labels() == labeled


def test_an_annotation_of_a_sample_the_catalog_no_longer_holds_comes_back_whole(timeline: LabelTimeline) -> None:
    kept = _annotation(UNCATALOGED_HASH, label="VOX")
    after_labeling = timeline.write(kept)
    timeline.clear(UNCATALOGED_HASH)

    timeline.restore(after_labeling)

    assert timeline.labels() == {UNCATALOGED_HASH: kept}


def test_a_dry_run_says_what_would_change_and_changes_nothing(timeline: LabelTimeline, connection: Connection) -> None:
    after_labeling = timeline.write(_annotation(KICK_HASH, label="KICK"))
    timeline.clear(KICK_HASH)

    plan = restore_annotations(connection, moment=after_labeling, apply=False)
    connection.commit()

    assert (len(plan.upserts), plan.removals) == (1, ())
    assert timeline.labels() == {}


def test_a_moment_before_the_history_begins_is_refused(timeline: LabelTimeline, connection: Connection) -> None:
    after_labeling = timeline.write(_annotation(KICK_HASH, label="KICK"))

    with pytest.raises(RestoreRefused, match="begins at"):
        restore_annotations(connection, moment=after_labeling - timedelta(days=1), apply=True)


def test_an_empty_history_is_refused(connection: Connection) -> None:
    with pytest.raises(RestoreRefused, match="nothing yet"):
        restore_annotations(connection, moment=datetime.now(UTC), apply=True)


def test_a_plan_writes_what_differs_and_clears_what_the_moment_did_not_hold() -> None:
    kick = _annotation(KICK_HASH, label="KICK")
    snare = _annotation(SNARE_HASH, label="SNARE")
    moment = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)

    plan = plan_restore(
        moment=moment,
        current={KICK_HASH: kick, UNCATALOGED_HASH: _annotation(UNCATALOGED_HASH, label="VOX")},
        target={KICK_HASH: kick, SNARE_HASH: snare},
    )

    assert (plan.upserts, plan.removals, plan.unchanged) == ((snare,), (UNCATALOGED_HASH,), 1)
