from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

import pytest
from sqlalchemy import Connection
from sqlalchemy.exc import IntegrityError

from samplecore.models.annotation import AnnotationSource, SampleAnnotation
from samplecore.models.sample_properties import SampleOccurrence
from samplecore.storage.curation import sample_annotation
from samplecore.storage.repositories import sample_annotation as sample_annotation_repository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository

THIRD_SAMPLE_HASH: Final[str] = "e" * 64


def _annotation(
    sample_hash: str,
    *,
    label: str | None = None,
    rating: int | None = None,
    favorite: bool = False,
    source: AnnotationSource = AnnotationSource.SAMPLE,
) -> SampleAnnotation:
    return SampleAnnotation(
        sample_hash=sample_hash,
        label=label,
        rating=rating,
        favorite=favorite,
        occurrence=SampleOccurrence(module_hash=format(7, "064x"), instrument_index=1, sample_slot=2),
        module_filename="song.it",
        sample_name="smp01",
        source=source,
        annotated_at=datetime.now(UTC),
    )


def _raw_values(sample_hash: str, *, rating: int | None, favorite: bool) -> dict[str, object]:
    """A row built past the model, for pinning guards the database holds on its own."""
    return {
        "sample_hash": sample_hash,
        "label": None,
        "rating": rating,
        "favorite": favorite,
        "module_hash": format(7, "064x"),
        "module_filename": "song.it",
        "instrument_index": 1,
        "sample_slot": 2,
        "sample_name": "smp01",
        "source": AnnotationSource.SAMPLE.value,
        "annotated_at": datetime.now(UTC),
    }


def test_an_annotation_round_trips_with_the_occurrence_it_was_anchored_to(
    connection: Connection, sample_hash_a: str
) -> None:
    repository = PostgresSampleAnnotationRepository(connection)
    annotation = _annotation(sample_hash_a, label="warm pad", rating=5, favorite=True)

    repository.replace_many((annotation,))

    assert repository.get(sample_hash_a) == annotation


@pytest.mark.parametrize(
    "decision",
    [
        {"label": "hat"},
        {"rating": 3},
        {"favorite": True},
        {"label": "hat", "rating": 3, "favorite": True},
    ],
)
def test_each_decision_a_person_can_record_alone_round_trips(
    decision: dict[str, object], connection: Connection, sample_hash_a: str
) -> None:
    repository = PostgresSampleAnnotationRepository(connection)
    annotation = _annotation(sample_hash_a, **decision)  # type: ignore[arg-type]

    repository.replace_many((annotation,))

    assert repository.get(sample_hash_a) == annotation


def test_an_annotation_is_kept_for_a_sample_the_catalog_does_not_hold(
    connection: Connection, sample_hash_a: str
) -> None:
    """No foreign key reaches the catalog, which lets a decision outlive the sample it names."""
    repository = PostgresSampleAnnotationRepository(connection)

    repository.replace_many((_annotation(sample_hash_a, label="vocal chop"),))

    assert repository.count() == 1


def test_writing_again_replaces_every_decision_including_the_ones_left_empty(
    connection: Connection, sample_hash_a: str
) -> None:
    """A write says what a sample carries from now on, so a decision left out is a decision undone."""
    repository = PostgresSampleAnnotationRepository(connection)
    repository.replace_many((_annotation(sample_hash_a, label="lead", rating=5, favorite=True),))

    repository.replace_many((_annotation(sample_hash_a, label="pluck"),))

    stored = repository.get(sample_hash_a)
    assert stored is not None
    assert (stored.label, stored.rating, stored.favorite) == ("PLUCK", None, False)
    assert repository.count() == 1


def test_a_row_recording_nothing_is_refused_by_the_database(connection: Connection, sample_hash_a: str) -> None:
    """The model refuses this too; here the table's own guard is pinned, which no path can slip past."""
    with pytest.raises(IntegrityError):
        connection.execute(sample_annotation.insert().values(_raw_values(sample_hash_a, rating=None, favorite=False)))

    connection.rollback()


@pytest.mark.parametrize("rating", [0, 6])
def test_a_rating_outside_the_scale_is_refused_by_the_database(
    rating: int, connection: Connection, sample_hash_a: str
) -> None:
    with pytest.raises(IntegrityError):
        connection.execute(sample_annotation.insert().values(_raw_values(sample_hash_a, rating=rating, favorite=True)))

    connection.rollback()


def test_annotating_a_group_writes_one_row_per_member(
    connection: Connection, sample_hash_a: str, sample_hash_b: str
) -> None:
    repository = PostgresSampleAnnotationRepository(connection)

    repository.replace_many(
        (
            _annotation(sample_hash_a, label="snare", source=AnnotationSource.EQUIVALENCE_CLASS),
            _annotation(sample_hash_b, label="snare", source=AnnotationSource.EQUIVALENCE_CLASS),
        )
    )

    stored = repository.annotations_by_hash([sample_hash_a, sample_hash_b])
    assert {hash_: item.label for hash_, item in stored.items()} == {
        sample_hash_a: "SNARE",
        sample_hash_b: "SNARE",
    }


def test_annotations_by_hash_reports_only_the_hashes_carrying_one(
    connection: Connection, sample_hash_a: str, sample_hash_b: str
) -> None:
    repository = PostgresSampleAnnotationRepository(connection)
    repository.replace_many((_annotation(sample_hash_a, label="kick"),))

    assert list(repository.annotations_by_hash([sample_hash_a, sample_hash_b])) == [sample_hash_a]


def test_annotations_by_hash_for_no_hashes_reads_nothing(connection: Connection) -> None:
    assert PostgresSampleAnnotationRepository(connection).annotations_by_hash([]) == {}


def test_annotations_by_hash_reads_more_hashes_than_one_statement_may_bind(
    connection: Connection, sample_hash_a: str, sample_hash_b: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sample_annotation_repository, "HASH_CHUNK_SIZE", 1)
    repository = PostgresSampleAnnotationRepository(connection)
    repository.replace_many((_annotation(sample_hash_a, label="kick"), _annotation(sample_hash_b, label="hat")))

    stored = repository.annotations_by_hash([sample_hash_a, sample_hash_b])
    assert {hash_: item.label for hash_, item in stored.items()} == {
        sample_hash_a: "KICK",
        sample_hash_b: "HAT",
    }


def test_writing_no_annotations_leaves_the_table_alone(connection: Connection) -> None:
    repository = PostgresSampleAnnotationRepository(connection)

    repository.replace_many(())

    assert repository.count() == 0


def test_deleting_reports_how_many_annotations_actually_went(
    connection: Connection, sample_hash_a: str, sample_hash_b: str
) -> None:
    repository = PostgresSampleAnnotationRepository(connection)
    repository.replace_many((_annotation(sample_hash_a, label="kick"),))

    assert repository.delete_many((sample_hash_a, sample_hash_b)) == 1
    assert repository.get(sample_hash_a) is None


def test_deleting_no_hashes_reads_as_nothing_removed(connection: Connection) -> None:
    assert PostgresSampleAnnotationRepository(connection).delete_many(()) == 0


def test_the_vocabulary_offers_the_most_used_wording_first(
    connection: Connection, sample_hash_a: str, sample_hash_b: str
) -> None:
    repository = PostgresSampleAnnotationRepository(connection)
    repository.replace_many(
        (
            _annotation(sample_hash_a, label="bass"),
            _annotation(sample_hash_b, label="bass"),
            _annotation(THIRD_SAMPLE_HASH, label="kick"),
        )
    )

    assert repository.vocabulary() == ("BASS", "KICK")


def test_the_vocabulary_passes_over_a_sample_carrying_no_wording(
    connection: Connection, sample_hash_a: str, sample_hash_b: str
) -> None:
    """A rating on its own says nothing about what to call a sample, so it offers no wording back."""
    repository = PostgresSampleAnnotationRepository(connection)
    repository.replace_many(
        (
            _annotation(sample_hash_a, label="bass"),
            _annotation(sample_hash_b, rating=5, favorite=True),
        )
    )

    assert repository.vocabulary() == ("BASS",)


def test_the_vocabulary_of_an_untouched_library_is_empty(connection: Connection) -> None:
    assert PostgresSampleAnnotationRepository(connection).vocabulary() == ()
