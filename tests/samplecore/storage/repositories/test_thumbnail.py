from __future__ import annotations

from sqlalchemy import Connection

from samplecore.models.sample import Sample
from samplecore.models.thumbnail import SampleThumbnail
from samplecore.storage.repositories.thumbnail import DuckDBSampleThumbnailRepository


def _thumbnail(sample_hash: str, *, bucket_count: int = 4) -> SampleThumbnail:
    return SampleThumbnail(
        sample_hash=sample_hash,
        bucket_count=bucket_count,
        minimums=tuple(-1.0 for _ in range(bucket_count)),
        maximums=tuple(1.0 for _ in range(bucket_count)),
    )


def test_get_for_a_sample_with_no_thumbnail_returns_none(connection: Connection, stored_sample: Sample) -> None:
    assert DuckDBSampleThumbnailRepository(connection).get(stored_sample.hash) is None


def test_a_thumbnail_round_trips_through_get(connection: Connection, stored_sample: Sample) -> None:
    repository = DuckDBSampleThumbnailRepository(connection)
    thumbnail = _thumbnail(stored_sample.hash)

    repository.upsert(thumbnail)

    assert repository.get(stored_sample.hash) == thumbnail


def test_upserting_the_same_sample_again_replaces_its_thumbnail(connection: Connection, stored_sample: Sample) -> None:
    repository = DuckDBSampleThumbnailRepository(connection)
    repository.upsert(_thumbnail(stored_sample.hash, bucket_count=4))
    refined = _thumbnail(stored_sample.hash, bucket_count=8)

    repository.upsert(refined)

    assert repository.get(stored_sample.hash) == refined


def test_get_many_returns_only_the_requested_hashes_that_have_a_thumbnail(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    repository = DuckDBSampleThumbnailRepository(connection)
    thumbnail = _thumbnail(stored_sample.hash)
    repository.upsert(thumbnail)

    result = repository.get_many([stored_sample.hash, stored_sample_b.hash])

    assert result == {stored_sample.hash: thumbnail}


def test_get_many_with_no_hashes_returns_nothing(connection: Connection) -> None:
    assert DuckDBSampleThumbnailRepository(connection).get_many([]) == {}
