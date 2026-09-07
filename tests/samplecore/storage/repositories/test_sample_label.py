from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

import pytest
from sqlalchemy import Connection

from samplecore.models.label import LabelSource, SampleLabel
from samplecore.models.sample_properties import SampleOccurrence
from samplecore.storage.repositories import sample_label as sample_label_repository
from samplecore.storage.repositories.sample_label import PostgresSampleLabelRepository

THIRD_SAMPLE_HASH: Final[str] = "e" * 64


def _label(sample_hash: str, text: str, *, source: LabelSource = LabelSource.SAMPLE) -> SampleLabel:
    return SampleLabel(
        sample_hash=sample_hash,
        label=text,
        occurrence=SampleOccurrence(module_hash=format(7, "064x"), instrument_index=1, sample_slot=2),
        module_filename="song.it",
        sample_name="smp01",
        source=source,
        labeled_at=datetime.now(UTC),
    )


def test_a_label_round_trips_with_the_occurrence_it_was_anchored_to(connection: Connection, sample_hash_a: str) -> None:
    repository = PostgresSampleLabelRepository(connection)
    label = _label(sample_hash_a, "warm pad")

    repository.upsert_many((label,))

    assert repository.get(sample_hash_a) == label


def test_a_label_is_kept_for_a_sample_the_catalog_does_not_hold(connection: Connection, sample_hash_a: str) -> None:
    """No foreign key reaches the catalog, which is what lets a label outlive the sample it names."""
    repository = PostgresSampleLabelRepository(connection)

    repository.upsert_many((_label(sample_hash_a, "vocal chop"),))

    assert repository.count() == 1


def test_relabelling_a_sample_replaces_what_was_there(connection: Connection, sample_hash_a: str) -> None:
    repository = PostgresSampleLabelRepository(connection)
    repository.upsert_many((_label(sample_hash_a, "lead"),))

    repository.upsert_many((_label(sample_hash_a, "pluck"),))

    stored = repository.get(sample_hash_a)
    assert stored is not None
    assert stored.label == "pluck"
    assert repository.count() == 1


def test_labelling_a_group_writes_one_row_per_member(
    connection: Connection, sample_hash_a: str, sample_hash_b: str
) -> None:
    repository = PostgresSampleLabelRepository(connection)

    repository.upsert_many(
        (
            _label(sample_hash_a, "snare", source=LabelSource.EQUIVALENCE_CLASS),
            _label(sample_hash_b, "snare", source=LabelSource.EQUIVALENCE_CLASS),
        )
    )

    assert repository.labels_by_hash([sample_hash_a, sample_hash_b]) == {
        sample_hash_a: "snare",
        sample_hash_b: "snare",
    }


def test_labels_by_hash_reports_only_the_hashes_carrying_one(
    connection: Connection, sample_hash_a: str, sample_hash_b: str
) -> None:
    repository = PostgresSampleLabelRepository(connection)
    repository.upsert_many((_label(sample_hash_a, "kick"),))

    assert repository.labels_by_hash([sample_hash_a, sample_hash_b]) == {sample_hash_a: "kick"}


def test_labels_by_hash_for_no_hashes_reads_nothing(connection: Connection) -> None:
    assert PostgresSampleLabelRepository(connection).labels_by_hash([]) == {}


def test_labels_by_hash_reads_more_hashes_than_one_statement_may_bind(
    connection: Connection, sample_hash_a: str, sample_hash_b: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sample_label_repository, "HASH_CHUNK_SIZE", 1)
    repository = PostgresSampleLabelRepository(connection)
    repository.upsert_many((_label(sample_hash_a, "kick"), _label(sample_hash_b, "hat")))

    assert repository.labels_by_hash([sample_hash_a, sample_hash_b]) == {
        sample_hash_a: "kick",
        sample_hash_b: "hat",
    }


def test_upserting_no_labels_leaves_the_table_alone(connection: Connection) -> None:
    repository = PostgresSampleLabelRepository(connection)

    repository.upsert_many(())

    assert repository.count() == 0


def test_deleting_reports_how_many_labels_actually_went(
    connection: Connection, sample_hash_a: str, sample_hash_b: str
) -> None:
    repository = PostgresSampleLabelRepository(connection)
    repository.upsert_many((_label(sample_hash_a, "kick"),))

    assert repository.delete_many((sample_hash_a, sample_hash_b)) == 1
    assert repository.get(sample_hash_a) is None


def test_deleting_no_hashes_reads_as_nothing_removed(connection: Connection) -> None:
    assert PostgresSampleLabelRepository(connection).delete_many(()) == 0


def test_the_vocabulary_offers_the_most_used_wording_first(
    connection: Connection, sample_hash_a: str, sample_hash_b: str
) -> None:
    repository = PostgresSampleLabelRepository(connection)
    repository.upsert_many(
        (
            _label(sample_hash_a, "bass"),
            _label(sample_hash_b, "bass"),
            _label(THIRD_SAMPLE_HASH, "kick"),
        )
    )

    assert repository.vocabulary() == ("bass", "kick")


def test_the_vocabulary_of_an_untouched_library_is_empty(connection: Connection) -> None:
    assert PostgresSampleLabelRepository(connection).vocabulary() == ()
