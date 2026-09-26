from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from sqlalchemy import Connection, func, select, text

from samplecore.models.annotation import (
    AnnotationDecisions,
    AnnotationSource,
    HistoryOperation,
    SampleAnnotation,
    SampleFileAnchor,
)
from samplecore.models.sample_file import SampleFileLocation
from samplecore.storage.curation import create_curation_schema
from samplecore.storage.repositories.annotation_history import PostgresAnnotationHistoryRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository

FIRST_HASH: Final[str] = "a" * 64
SECOND_HASH: Final[str] = "b" * 64
HISTORY_LIMIT: Final[int] = 100
DROP_HISTORY: Final[tuple[str, ...]] = (
    "DROP TRIGGER sample_annotation_history ON curation.sample_annotation",
    "DROP FUNCTION curation.record_annotation_change()",
    "DROP TABLE curation.annotation_history",
)


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


def _write(connection: Connection, *annotations: SampleAnnotation) -> None:
    PostgresSampleAnnotationRepository(connection).upsert_many(annotations)
    connection.commit()


def _clear(connection: Connection, sample_hash: str) -> None:
    PostgresSampleAnnotationRepository(connection).delete_many((sample_hash,))
    connection.commit()


def _now(connection: Connection) -> datetime:
    moment: datetime = connection.execute(select(func.clock_timestamp())).scalar_one()
    connection.commit()
    return moment


def _changes(
    connection: Connection,
) -> tuple[tuple[HistoryOperation, AnnotationDecisions | None, AnnotationDecisions | None], ...]:
    history = PostgresAnnotationHistoryRepository(connection).changes(sample_hash=None, since=None, limit=HISTORY_LIMIT)
    return tuple((change.operation, change.previous, change.current) for change in history)


def _decisions(label: str | None, rating: int | None = None) -> AnnotationDecisions:
    return AnnotationDecisions(label=label, rating=rating, favorite=False)


def test_every_insert_update_and_delete_is_recorded_with_the_row_before_and_after(connection: Connection) -> None:
    _write(connection, _annotation(FIRST_HASH, label="SNARE"))
    _write(connection, _annotation(FIRST_HASH, label="SNARE: RIM", rating=4))
    _clear(connection, FIRST_HASH)

    assert _changes(connection) == (
        (HistoryOperation.INSERT, None, _decisions("SNARE")),
        (HistoryOperation.UPDATE, _decisions("SNARE"), _decisions("SNARE: RIM", 4)),
        (HistoryOperation.DELETE, _decisions("SNARE: RIM", 4), None),
    )


def test_a_write_changing_nothing_leaves_no_entry(connection: Connection) -> None:
    _write(connection, _annotation(FIRST_HASH, label="SNARE"))
    _write(connection, _annotation(FIRST_HASH, label="SNARE"))

    assert len(_changes(connection)) == 1


def test_one_write_over_a_group_is_recorded_at_one_moment_by_the_role_that_made_it(connection: Connection) -> None:
    _write(connection, _annotation(FIRST_HASH, label="KICK"), _annotation(SECOND_HASH, label="KICK"))

    history = PostgresAnnotationHistoryRepository(connection).changes(sample_hash=None, since=None, limit=HISTORY_LIMIT)
    login_role = connection.execute(select(func.session_user())).scalar_one()
    assert len({change.recorded_at for change in history}) == 1
    assert {change.role for change in history} == {login_role}


def test_the_history_begins_with_every_annotation_standing_when_it_is_created(connection: Connection) -> None:
    for statement in DROP_HISTORY:
        connection.execute(text(statement))
    _write(connection, _annotation(FIRST_HASH, label="PAD"), _annotation(SECOND_HASH, label=None, rating=2))

    create_curation_schema(connection)
    connection.commit()

    assert set(_changes(connection)) == {
        (HistoryOperation.BASELINE, None, _decisions("PAD")),
        (HistoryOperation.BASELINE, None, _decisions(None, 2)),
    }


def test_the_annotations_read_back_as_they_stood_at_each_moment(connection: Connection) -> None:
    history = PostgresAnnotationHistoryRepository(connection)
    labeled = _annotation(FIRST_HASH, label="LEAD")
    relabeled = _annotation(FIRST_HASH, label="LEAD: SAW")
    _write(connection, labeled)
    after_labeling = _now(connection)
    _write(connection, relabeled)
    after_relabeling = _now(connection)
    _clear(connection, FIRST_HASH)
    after_clearing = _now(connection)

    assert history.annotations_as_of(after_labeling) == (labeled,)
    assert history.annotations_as_of(after_relabeling) == (relabeled,)
    assert history.annotations_as_of(after_clearing) == ()
    assert history.started_at() is not None
