from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Connection

from samplecore.models.annotation import SampleAnnotation
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository
from sampleextract.annotations.relink import relink_annotations


def test_a_label_follows_its_sample_through_a_change_of_hash(
    connection: Connection, stored_annotation: SampleAnnotation, rehash_the_labeled_sample: Callable[[], str]
) -> None:
    """The anchor is the whole point of storing the occurrence: the slot outlives the hash."""
    current_hash = rehash_the_labeled_sample()

    summary = relink_annotations(connection)

    assert summary.relinked == 1
    repository = PostgresSampleAnnotationRepository(connection)
    assert repository.get(stored_annotation.sample_hash) is None
    recovered = repository.get(current_hash)
    assert recovered is not None
    assert recovered.label == stored_annotation.label
    assert recovered.occurrence == stored_annotation.occurrence


def test_a_label_whose_sample_is_still_cataloged_is_left_exactly_as_it_is(
    connection: Connection, stored_annotation: SampleAnnotation
) -> None:
    summary = relink_annotations(connection)

    assert summary.stale == 0
    assert summary.relinked == 0
    assert PostgresSampleAnnotationRepository(connection).get(stored_annotation.sample_hash) == stored_annotation


def test_a_label_whose_slot_is_gone_is_reported_and_kept(
    connection: Connection, stored_annotation: SampleAnnotation, forget_the_labeled_occurrence: Callable[[], None]
) -> None:
    """Nothing is thrown away on a person's behalf: an unresolvable label stays on file, reported."""
    forget_the_labeled_occurrence()

    summary = relink_annotations(connection)

    assert summary.stale == 1
    assert summary.relinked == 0
    assert [label.sample_hash for label in summary.unresolved] == [stored_annotation.sample_hash]
    assert PostgresSampleAnnotationRepository(connection).get(stored_annotation.sample_hash) == stored_annotation


def test_relinking_an_unlabeled_library_finds_nothing_to_do(connection: Connection) -> None:
    summary = relink_annotations(connection)

    assert summary.checked == 0
    assert summary.unresolved == ()


def test_a_label_whose_slot_now_holds_an_annotated_sample_is_left_for_a_person(
    connection: Connection, stored_annotation: SampleAnnotation, rehash_the_labeled_sample: Callable[[], str]
) -> None:
    """The sample in the slot already says something of its own, and relinking keeps both decisions."""
    current_hash = rehash_the_labeled_sample()
    repository = PostgresSampleAnnotationRepository(connection)
    newer = stored_annotation.model_copy(update={"sample_hash": current_hash, "label": "BRIGHT PAD", "rating": 2})
    repository.upsert_many((newer,))
    connection.commit()

    summary = relink_annotations(connection)

    assert [annotation.sample_hash for annotation in summary.conflicting] == [stored_annotation.sample_hash]
    assert summary.needs_a_person
    assert repository.get(current_hash) == newer
    assert repository.get(stored_annotation.sample_hash) == stored_annotation
