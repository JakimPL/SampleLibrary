from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Connection

from samplecore.models.label import SampleLabel
from samplecore.storage.repositories.sample_label import PostgresSampleLabelRepository
from sampleextract.labels.relink import relink_labels


def test_a_label_follows_its_sample_through_a_change_of_hash(
    connection: Connection, stored_label: SampleLabel, rehash_the_labelled_sample: Callable[[], str]
) -> None:
    """The anchor is the whole point of storing the occurrence: the slot outlives the hash."""
    current_hash = rehash_the_labelled_sample()

    summary = relink_labels(connection)

    assert summary.relinked == 1
    repository = PostgresSampleLabelRepository(connection)
    assert repository.get(stored_label.sample_hash) is None
    recovered = repository.get(current_hash)
    assert recovered is not None
    assert recovered.label == stored_label.label
    assert recovered.occurrence == stored_label.occurrence


def test_a_label_whose_sample_is_still_catalogued_is_left_exactly_as_it_is(
    connection: Connection, stored_label: SampleLabel
) -> None:
    summary = relink_labels(connection)

    assert summary.stale == 0
    assert summary.relinked == 0
    assert PostgresSampleLabelRepository(connection).get(stored_label.sample_hash) == stored_label


def test_a_label_whose_slot_is_gone_is_reported_and_kept(
    connection: Connection, stored_label: SampleLabel, forget_the_labelled_occurrence: Callable[[], None]
) -> None:
    """Nothing is thrown away on a person's behalf: an unresolvable label stays on file, reported."""
    forget_the_labelled_occurrence()

    summary = relink_labels(connection)

    assert summary.stale == 1
    assert summary.relinked == 0
    assert [label.sample_hash for label in summary.unresolved] == [stored_label.sample_hash]
    assert PostgresSampleLabelRepository(connection).get(stored_label.sample_hash) == stored_label


def test_relinking_an_unlabelled_library_finds_nothing_to_do(connection: Connection) -> None:
    summary = relink_labels(connection)

    assert summary.checked == 0
    assert summary.unresolved == ()
