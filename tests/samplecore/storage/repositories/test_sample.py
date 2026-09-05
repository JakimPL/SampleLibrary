from __future__ import annotations

import duckdb
from trackmod.core.samples.depth import BitDepth
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.channels import ChannelLayout
from samplecore.models.module import Module
from samplecore.models.sample import Sample
from samplecore.models.sample_properties import SampleOccurrence, XMSampleProperties
from samplecore.models.thumbnail import SampleThumbnail
from samplecore.storage.repositories.sample import DuckDBSampleRepository
from samplecore.storage.repositories.sample_properties import DuckDBSamplePropertiesRepository
from samplecore.storage.repositories.thumbnail import DuckDBSampleThumbnailRepository


def _add_occurrence(
    connection: duckdb.DuckDBPyConnection, *, sample: Sample, module: Module, slot: int, name: str, rate: int = 8363
) -> None:
    DuckDBSamplePropertiesRepository(connection).upsert(
        XMSampleProperties(
            sample_hash=sample.hash,
            occurrence=SampleOccurrence(module_hash=module.hash, instrument_index=0, sample_slot=slot),
            name=name,
            rate=rate,
            volume=64,
            tuning=Tuning(relative_note=0, finetune=0),
        )
    )


def test_a_stored_sample_round_trips_through_get(connection: duckdb.DuckDBPyConnection, sample_hash_a: str) -> None:
    repository = DuckDBSampleRepository(connection)
    sample = Sample(hash=sample_hash_a, depth=BitDepth.EIGHT, channels=ChannelLayout.STEREO, frames=12)

    repository.upsert(sample)

    assert repository.get(sample_hash_a) == sample


def test_get_on_an_unknown_hash_returns_none(connection: duckdb.DuckDBPyConnection, sample_hash_a: str) -> None:
    repository = DuckDBSampleRepository(connection)

    assert repository.get(sample_hash_a) is None


def test_upserting_the_same_sample_twice_does_not_raise(
    connection: duckdb.DuckDBPyConnection, sample_hash_a: str
) -> None:
    repository = DuckDBSampleRepository(connection)
    sample = Sample(hash=sample_hash_a, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=4)

    repository.upsert(sample)
    repository.upsert(sample)

    assert repository.get(sample_hash_a) == sample


def test_list_all_on_an_empty_catalog_returns_nothing(connection: duckdb.DuckDBPyConnection) -> None:
    assert DuckDBSampleRepository(connection).list_all() == ()


def test_list_all_returns_every_stored_sample(
    connection: duckdb.DuckDBPyConnection, sample_hash_a: str, sample_hash_b: str
) -> None:
    repository = DuckDBSampleRepository(connection)
    first = Sample(hash=sample_hash_a, depth=BitDepth.EIGHT, channels=ChannelLayout.MONO, frames=4)
    second = Sample(hash=sample_hash_b, depth=BitDepth.SIXTEEN, channels=ChannelLayout.STEREO, frames=16)
    repository.upsert(first)
    repository.upsert(second)

    assert set(repository.list_all()) == {first, second}


def test_list_page_on_an_empty_catalog_returns_nothing(connection: duckdb.DuckDBPyConnection) -> None:
    assert DuckDBSampleRepository(connection).list_page(limit=50, offset=0) == ()


def test_list_page_ranks_by_occurrence_count_descending(
    connection: duckdb.DuckDBPyConnection, stored_sample: Sample, stored_sample_b: Sample, stored_module: Module
) -> None:
    _add_occurrence(connection, sample=stored_sample, module=stored_module, slot=0, name="kick")
    _add_occurrence(connection, sample=stored_sample, module=stored_module, slot=1, name="kick")

    page = DuckDBSampleRepository(connection).list_page(limit=50, offset=0)

    assert [summary.hash for summary in page] == [stored_sample.hash, stored_sample_b.hash]
    assert page[0].occurrence_count == 2
    assert page[1].occurrence_count == 0


def test_list_page_breaks_a_tied_occurrence_count_by_hash(
    connection: duckdb.DuckDBPyConnection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    page = DuckDBSampleRepository(connection).list_page(limit=50, offset=0)

    assert [summary.hash for summary in page] == sorted([stored_sample.hash, stored_sample_b.hash])


def test_list_page_respects_limit_and_offset(
    connection: duckdb.DuckDBPyConnection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    page = DuckDBSampleRepository(connection).list_page(limit=1, offset=1)

    assert len(page) == 1
    assert page[0].hash == sorted([stored_sample.hash, stored_sample_b.hash])[1]


def test_list_page_resolves_the_dominant_occurrence_name(
    connection: duckdb.DuckDBPyConnection, stored_sample: Sample, stored_module: Module
) -> None:
    _add_occurrence(connection, sample=stored_sample, module=stored_module, slot=0, name="kick")
    _add_occurrence(connection, sample=stored_sample, module=stored_module, slot=1, name="KICK")

    page = DuckDBSampleRepository(connection).list_page(limit=50, offset=0)

    assert page[0].display_name == "kick"


def test_list_page_resolves_the_dominant_occurrence_rate(
    connection: duckdb.DuckDBPyConnection, stored_sample: Sample, stored_module: Module
) -> None:
    _add_occurrence(connection, sample=stored_sample, module=stored_module, slot=0, name="kick", rate=8363)
    _add_occurrence(connection, sample=stored_sample, module=stored_module, slot=1, name="kick", rate=8363)
    _add_occurrence(connection, sample=stored_sample, module=stored_module, slot=2, name="kick", rate=22050)

    page = DuckDBSampleRepository(connection).list_page(limit=50, offset=0)

    assert page[0].dominant_rate_hz == 8363


def test_list_page_leaves_dominant_rate_none_for_a_sample_with_no_occurrences(
    connection: duckdb.DuckDBPyConnection, stored_sample: Sample
) -> None:
    page = DuckDBSampleRepository(connection).list_page(limit=50, offset=0)

    assert page[0].dominant_rate_hz is None


def test_list_page_resolves_size_bytes_from_the_sample_itself(
    connection: duckdb.DuckDBPyConnection, stored_sample: Sample
) -> None:
    page = DuckDBSampleRepository(connection).list_page(limit=50, offset=0)

    assert page[0].size_bytes == stored_sample.stored_bytes


def test_list_page_leaves_thumbnail_none_for_a_sample_not_yet_thumbnailed(
    connection: duckdb.DuckDBPyConnection, stored_sample: Sample
) -> None:
    page = DuckDBSampleRepository(connection).list_page(limit=50, offset=0)

    assert page[0].thumbnail is None


def test_list_page_resolves_a_cached_thumbnail(connection: duckdb.DuckDBPyConnection, stored_sample: Sample) -> None:
    DuckDBSampleThumbnailRepository(connection).upsert(
        SampleThumbnail(sample_hash=stored_sample.hash, bucket_count=2, minimums=(-1.0, -0.5), maximums=(0.5, 1.0))
    )

    page = DuckDBSampleRepository(connection).list_page(limit=50, offset=0)

    assert page[0].thumbnail is not None
    assert [peak.minimum for peak in page[0].thumbnail] == [-1.0, -0.5]
    assert [peak.maximum for peak in page[0].thumbnail] == [0.5, 1.0]


def test_get_many_returns_only_the_requested_hashes_that_exist(
    connection: duckdb.DuckDBPyConnection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    result = DuckDBSampleRepository(connection).get_many([stored_sample.hash, "f" * 64])

    assert result == {stored_sample.hash: stored_sample}


def test_get_many_with_no_hashes_returns_nothing(connection: duckdb.DuckDBPyConnection) -> None:
    assert DuckDBSampleRepository(connection).get_many([]) == {}


def test_count_reflects_every_stored_sample(
    connection: duckdb.DuckDBPyConnection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    assert DuckDBSampleRepository(connection).count() == 2
