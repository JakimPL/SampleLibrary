from __future__ import annotations

from sqlalchemy import Connection

from samplecore.models.sample import Sample
from samplecore.storage.repositories.playback_rate import PostgresSamplePlaybackRateRepository


def test_a_recorded_rate_round_trips_through_a_by_hash_lookup(connection: Connection, stored_sample: Sample) -> None:
    repository = PostgresSamplePlaybackRateRepository(connection)

    repository.replace_all({stored_sample.hash: 16726})

    assert repository.get_many([stored_sample.hash]) == {stored_sample.hash: 16726}


def test_every_recorded_rate_is_readable_at_once(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    repository = PostgresSamplePlaybackRateRepository(connection)

    repository.replace_all({stored_sample.hash: 8363, stored_sample_b.hash: 22050})

    assert repository.list_all() == {stored_sample.hash: 8363, stored_sample_b.hash: 22050}


def test_a_later_pass_replaces_every_rate_an_earlier_one_left(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    """One pass answers for the whole catalog, so a sample missing from it has no rate any more."""
    repository = PostgresSamplePlaybackRateRepository(connection)
    repository.replace_all({stored_sample.hash: 8363, stored_sample_b.hash: 22050})

    repository.replace_all({stored_sample_b.hash: 11025})

    assert repository.list_all() == {stored_sample_b.hash: 11025}


def test_a_sample_with_no_recorded_rate_is_left_out_of_a_lookup(connection: Connection, stored_sample: Sample) -> None:
    assert PostgresSamplePlaybackRateRepository(connection).get_many([stored_sample.hash]) == {}


def test_a_lookup_naming_no_hashes_returns_nothing(connection: Connection) -> None:
    assert PostgresSamplePlaybackRateRepository(connection).get_many([]) == {}
