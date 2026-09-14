from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

from sqlalchemy import Connection

from samplecore.models.annotation import (
    AnnotationChanges,
    AnnotationDecision,
    AnnotationDecisions,
    AnnotationSource,
    ModuleSlotAnchor,
    SampleAnnotation,
)
from samplecore.models.sample_properties import SampleOccurrence
from samplecore.storage.annotation_writes import (
    AnnotationWrite,
    WrittenDecisions,
    plan_annotation_write,
    write_annotation_changes,
)
from samplecore.storage.curation import read_tag_ranks, register_tag_ranks, sample_annotation
from samplecore.storage.database import connect, start_batch
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository

FIRST = "a" * 64
SECOND = "b" * 64
EARLIER = datetime(2026, 1, 1, tzinfo=UTC)
NOW = datetime(2026, 9, 14, tzinfo=UTC)
ANCHOR = ModuleSlotAnchor(
    occurrence=SampleOccurrence(module_hash="c" * 64, instrument_index=0, sample_slot=1),
    module_filename="song.xm",
    sample_name="lead",
)


def _stored(sample_hash: str, *, label: str | None, rating: int | None = None) -> SampleAnnotation:
    return SampleAnnotation(
        sample_hash=sample_hash,
        label=label,
        rating=rating,
        favorite=False,
        anchor=ANCHOR,
        source=AnnotationSource.SAMPLE,
        annotated_at=EARLIER,
    )


def _write(sample_hashes: tuple[str, ...], changes: AnnotationChanges) -> AnnotationWrite:
    return AnnotationWrite(
        sample_hashes=sample_hashes, changes=changes, source=AnnotationSource.SAMPLE, annotated_at=NOW
    )


def _changing(**decisions: object) -> AnnotationChanges:
    values = AnnotationDecisions.model_validate({"label": None, "rating": None, "favorite": False} | decisions)
    return AnnotationChanges(values=values, changed=frozenset(AnnotationDecision(name) for name in decisions))


def test_a_sample_the_change_leaves_as_it_was_is_not_rewritten() -> None:
    plan = plan_annotation_write(
        _write((FIRST,), _changing(rating=3)),
        existing={FIRST: _stored(FIRST, label="KICK", rating=3)},
        anchors={FIRST: ANCHOR},
    )

    assert (plan.upserts, plan.removals) == ((), ())
    assert plan.written == (WrittenDecisions(FIRST, AnnotationDecisions(label="KICK", rating=3, favorite=False)),)


def test_a_sample_left_saying_nothing_is_removed() -> None:
    plan = plan_annotation_write(
        _write((FIRST,), _changing(label=None)), existing={FIRST: _stored(FIRST, label="KICK")}, anchors={}
    )

    assert plan.removals == (FIRST,)
    assert plan.written == (WrittenDecisions(FIRST, None),)


def test_a_sample_given_a_first_decision_with_nothing_to_anchor_it_is_skipped() -> None:
    plan = plan_annotation_write(
        _write((FIRST, SECOND), _changing(label="snare")), existing={}, anchors={FIRST: ANCHOR}
    )

    assert [annotation.sample_hash for annotation in plan.upserts] == [FIRST]
    assert plan.skipped == (SECOND,)


def test_two_writers_changing_different_decisions_of_one_sample_both_land(
    connection: Connection, _database_url: str
) -> None:
    """Each writer reads what the other committed once it holds the write lock, so neither change is lost."""
    PostgresSampleAnnotationRepository(connection).upsert_many((_stored(FIRST, label="KICK"),))
    connection.commit()
    ready = threading.Barrier(2)

    def write(changes: AnnotationChanges) -> None:
        writer = connect(_database_url)
        try:
            ready.wait()
            write_annotation_changes(writer, _write((FIRST,), changes), anchors={FIRST: ANCHOR})
        finally:
            writer.close()

    writers = [
        threading.Thread(target=write, args=(_changing(rating=5),)),
        threading.Thread(target=write, args=(_changing(favorite=True),)),
    ]
    for writer in writers:
        writer.start()
    for writer in writers:
        writer.join()

    stored = PostgresSampleAnnotationRepository(connection).get(FIRST)
    assert stored is not None
    assert (stored.label, stored.rating, stored.favorite) == ("KICK", 5, True)


def test_a_new_tag_takes_the_rank_after_the_last_and_known_tags_keep_theirs(connection: Connection) -> None:
    with start_batch(connection):
        register_tag_ranks(connection, ["SNARE", "HI-HAT: CLOSED"])
        register_tag_ranks(connection, ["KICK, SNARE"])

    assert read_tag_ranks(connection) == {("SNARE",): 0, ("HI-HAT",): 1, ("HI-HAT", "CLOSED"): 2, ("KICK",): 3}


def test_ranks_are_seeded_from_labels_in_the_order_they_were_first_used(
    connection: Connection, _database_url: str
) -> None:
    """A library labeled before ranks were kept gets them in the order its tags were first used."""
    connection.execute(
        sample_annotation.insert(),
        [
            _row(FIRST, label="SNARE", annotated_at=EARLIER + timedelta(days=2)),
            _row(SECOND, label="KICK", annotated_at=EARLIER),
        ],
    )
    connection.commit()

    opened = connect(_database_url)
    try:
        assert read_tag_ranks(opened) == {("KICK",): 0, ("SNARE",): 1}
    finally:
        opened.close()


def _row(sample_hash: str, *, label: str, annotated_at: datetime) -> dict[str, object]:
    return {
        "sample_hash": sample_hash,
        "label": label,
        "rating": None,
        "favorite": False,
        "module_hash": ANCHOR.occurrence.module_hash,
        "module_filename": ANCHOR.module_filename,
        "instrument_index": ANCHOR.occurrence.instrument_index,
        "sample_slot": ANCHOR.occurrence.sample_slot,
        "sample_name": ANCHOR.sample_name,
        "file_directory": None,
        "file_relative_path": None,
        "source": AnnotationSource.SAMPLE.value,
        "annotated_at": annotated_at,
    }
