from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import Connection
from trackmod.core.instruments.behavior import DuplicateAction, DuplicateCheck, NewNoteAction
from trackmod.core.samples.depth import BitDepth
from trackmod.trackers.xm.tuning import Tuning

from samplecore.equivalence_classes import EquivalenceClass
from samplecore.models.annotation import AnnotationSource, SampleAnnotation
from samplecore.models.category import SampleCategory
from samplecore.models.channels import ChannelLayout
from samplecore.models.module import Module
from samplecore.models.module_instrument import ModuleInstrument
from samplecore.models.sample import Sample, SampleSelection, SampleSort
from samplecore.models.sample_properties import SampleOccurrence, XMSampleProperties
from samplecore.models.thumbnail import SampleThumbnail
from samplecore.storage.repositories import sample as sample_repository
from samplecore.storage.repositories.module_instrument import PostgresModuleInstrumentRepository
from samplecore.storage.repositories.playback_rate import PostgresSamplePlaybackRateRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository
from samplecore.storage.repositories.thumbnail import PostgresSampleThumbnailRepository

EVERYTHING = SampleSelection()
"""Every sample, in the listing's own order: the selection a test makes when it is about something else."""


def _add_occurrence(
    connection: Connection, *, sample: Sample, module: Module, slot: int, name: str, rate: int = 8363
) -> None:
    PostgresSamplePropertiesRepository(connection).upsert(
        XMSampleProperties(
            sample_hash=sample.hash,
            occurrence=SampleOccurrence(module_hash=module.hash, instrument_index=0, sample_slot=slot),
            name=name,
            rate=rate,
            volume=64,
            tuning=Tuning(relative_note=0, finetune=0),
        )
    )


def test_a_stored_sample_round_trips_through_get(connection: Connection, sample_hash_a: str) -> None:
    repository = PostgresSampleRepository(connection)
    sample = Sample(hash=sample_hash_a, depth=BitDepth.EIGHT, channels=ChannelLayout.STEREO, frames=12)

    repository.upsert(sample)

    assert repository.get(sample_hash_a) == sample


def test_get_on_an_unknown_hash_returns_none(connection: Connection, sample_hash_a: str) -> None:
    repository = PostgresSampleRepository(connection)

    assert repository.get(sample_hash_a) is None


def test_upserting_the_same_sample_twice_does_not_raise(connection: Connection, sample_hash_a: str) -> None:
    repository = PostgresSampleRepository(connection)
    sample = Sample(hash=sample_hash_a, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=4)

    repository.upsert(sample)
    repository.upsert(sample)

    assert repository.get(sample_hash_a) == sample


def test_list_all_on_an_empty_catalog_returns_nothing(connection: Connection) -> None:
    assert PostgresSampleRepository(connection).list_all() == ()


def test_list_all_returns_every_stored_sample(connection: Connection, sample_hash_a: str, sample_hash_b: str) -> None:
    repository = PostgresSampleRepository(connection)
    first = Sample(hash=sample_hash_a, depth=BitDepth.EIGHT, channels=ChannelLayout.MONO, frames=4)
    second = Sample(hash=sample_hash_b, depth=BitDepth.SIXTEEN, channels=ChannelLayout.STEREO, frames=16)
    repository.upsert(first)
    repository.upsert(second)

    assert set(repository.list_all()) == {first, second}


def test_list_page_on_an_empty_catalog_returns_nothing(connection: Connection) -> None:
    assert (
        PostgresSampleRepository(connection).list_page(limit=50, offset=0, class_by_hash={}, selection=EVERYTHING) == ()
    )


def test_list_page_ranks_by_occurrence_count_descending(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample, stored_module: Module
) -> None:
    _add_occurrence(connection, sample=stored_sample, module=stored_module, slot=0, name="kick")
    _add_occurrence(connection, sample=stored_sample, module=stored_module, slot=1, name="kick")

    page = PostgresSampleRepository(connection).list_page(limit=50, offset=0, class_by_hash={}, selection=EVERYTHING)

    assert [summary.hash for summary in page] == [stored_sample.hash, stored_sample_b.hash]
    assert page[0].occurrence_count == 2
    assert page[1].occurrence_count == 0


def test_list_page_breaks_a_tied_occurrence_count_by_hash(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    page = PostgresSampleRepository(connection).list_page(limit=50, offset=0, class_by_hash={}, selection=EVERYTHING)

    assert [summary.hash for summary in page] == sorted([stored_sample.hash, stored_sample_b.hash])


def test_list_page_respects_limit_and_offset(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    page = PostgresSampleRepository(connection).list_page(limit=1, offset=1, class_by_hash={}, selection=EVERYTHING)

    assert len(page) == 1
    assert page[0].hash == sorted([stored_sample.hash, stored_sample_b.hash])[1]


def test_list_page_resolves_the_dominant_occurrence_name(
    connection: Connection, stored_sample: Sample, stored_module: Module
) -> None:
    _add_occurrence(connection, sample=stored_sample, module=stored_module, slot=0, name="kick")
    _add_occurrence(connection, sample=stored_sample, module=stored_module, slot=1, name="KICK")

    page = PostgresSampleRepository(connection).list_page(limit=50, offset=0, class_by_hash={}, selection=EVERYTHING)

    assert page[0].display_name == "kick"


def test_list_page_plays_a_sample_at_the_rate_its_note_events_settle_on(
    connection: Connection, stored_sample: Sample, stored_module: Module
) -> None:
    """A recorded rate says how the library really sounds a sample, whatever its occurrences declare."""
    _add_occurrence(connection, sample=stored_sample, module=stored_module, slot=0, name="kick", rate=8363)
    PostgresSamplePlaybackRateRepository(connection).replace_all({stored_sample.hash: 16726})

    page = PostgresSampleRepository(connection).list_page(limit=50, offset=0, class_by_hash={}, selection=EVERYTHING)

    assert page[0].playback_rate_hz == 16726


def test_list_page_falls_back_to_the_dominant_occurrence_rate_where_no_pattern_plays_a_sample(
    connection: Connection, stored_sample: Sample, stored_module: Module
) -> None:
    _add_occurrence(connection, sample=stored_sample, module=stored_module, slot=0, name="kick", rate=8363)
    _add_occurrence(connection, sample=stored_sample, module=stored_module, slot=1, name="kick", rate=8363)
    _add_occurrence(connection, sample=stored_sample, module=stored_module, slot=2, name="kick", rate=22050)

    page = PostgresSampleRepository(connection).list_page(limit=50, offset=0, class_by_hash={}, selection=EVERYTHING)

    assert page[0].playback_rate_hz == 8363


def test_list_page_leaves_the_playback_rate_none_for_a_sample_with_no_occurrences(
    connection: Connection, stored_sample: Sample
) -> None:
    page = PostgresSampleRepository(connection).list_page(limit=50, offset=0, class_by_hash={}, selection=EVERYTHING)

    assert page[0].playback_rate_hz is None


def test_list_page_resolves_size_bytes_from_the_sample_itself(connection: Connection, stored_sample: Sample) -> None:
    page = PostgresSampleRepository(connection).list_page(limit=50, offset=0, class_by_hash={}, selection=EVERYTHING)

    assert page[0].size_bytes == stored_sample.stored_bytes


def test_list_page_leaves_thumbnail_none_for_a_sample_not_yet_thumbnailed(
    connection: Connection, stored_sample: Sample
) -> None:
    page = PostgresSampleRepository(connection).list_page(limit=50, offset=0, class_by_hash={}, selection=EVERYTHING)

    assert page[0].thumbnail is None


def test_list_page_resolves_a_cached_thumbnail(connection: Connection, stored_sample: Sample) -> None:
    PostgresSampleThumbnailRepository(connection).upsert(
        SampleThumbnail(sample_hash=stored_sample.hash, bucket_count=2, minimums=(-1.0, -0.5), maximums=(0.5, 1.0))
    )

    page = PostgresSampleRepository(connection).list_page(limit=50, offset=0, class_by_hash={}, selection=EVERYTHING)

    assert page[0].thumbnail is not None
    assert [peak.minimum for peak in page[0].thumbnail] == [-1.0, -0.5]
    assert [peak.maximum for peak in page[0].thumbnail] == [0.5, 1.0]


def test_list_page_leaves_equivalence_fields_at_their_standalone_default(
    connection: Connection, stored_sample: Sample
) -> None:
    page = PostgresSampleRepository(connection).list_page(limit=50, offset=0, class_by_hash={}, selection=EVERYTHING)

    assert page[0].equivalence_class_hash is None
    assert page[0].equivalence_member_count == 1


def test_list_page_resolves_a_sample_s_equivalence_class(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    equivalence_class = EquivalenceClass(class_hash="c" * 64, member_hashes=(stored_sample.hash, stored_sample_b.hash))

    page = PostgresSampleRepository(connection).list_page(
        limit=50, offset=0, class_by_hash={stored_sample.hash: equivalence_class}, selection=EVERYTHING
    )

    by_hash = {summary.hash: summary for summary in page}
    assert by_hash[stored_sample.hash].equivalence_class_hash == equivalence_class.class_hash
    assert by_hash[stored_sample.hash].equivalence_member_count == 2
    assert by_hash[stored_sample_b.hash].equivalence_class_hash is None
    assert by_hash[stored_sample_b.hash].equivalence_member_count == 1


def test_get_many_returns_only_the_requested_hashes_that_exist(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    result = PostgresSampleRepository(connection).get_many([stored_sample.hash, "f" * 64])

    assert result == {stored_sample.hash: stored_sample}


def test_get_many_with_no_hashes_returns_nothing(connection: Connection) -> None:
    assert PostgresSampleRepository(connection).get_many([]) == {}


def test_count_reflects_every_stored_sample(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    assert PostgresSampleRepository(connection).count(selection=EVERYTHING) == 2


def test_names_and_rates_by_hash_covers_hashes_spanning_several_chunks(
    connection: Connection,
    monkeypatch: pytest.MonkeyPatch,
    stored_sample: Sample,
    stored_sample_b: Sample,
    stored_module: Module,
) -> None:
    """A lookup larger than one chunk still reports every hash it was asked about.

    Postgres binds a limited number of parameters to one statement, which a whole-catalog lookup
    exceeds, so the query runs in chunks; shrinking the chunk size exercises that split over a
    catalog small enough to keep the test fast.
    """
    monkeypatch.setattr(sample_repository, "HASH_CHUNK_SIZE", 1)
    _add_occurrence(connection, sample=stored_sample, module=stored_module, slot=0, name="kick", rate=8363)
    _add_occurrence(connection, sample=stored_sample_b, module=stored_module, slot=1, name="snare", rate=16000)

    names_by_hash, rates_by_hash = PostgresSampleRepository(connection).names_and_rates_by_hash(
        [stored_sample.hash, stored_sample_b.hash]
    )

    assert names_by_hash == {stored_sample.hash: ("kick",), stored_sample_b.hash: ("snare",)}
    assert rates_by_hash == {stored_sample.hash: (8363,), stored_sample_b.hash: (16000,)}


def test_names_and_rates_by_hash_with_no_hashes_returns_nothing(connection: Connection) -> None:
    assert PostgresSampleRepository(connection).names_and_rates_by_hash([]) == ({}, {})


def _add_instrument(connection: Connection, *, module: Module, instrument_index: int, name: str) -> None:
    PostgresModuleInstrumentRepository(connection).insert_many(
        [
            ModuleInstrument(
                module_id=module.id,
                instrument_index=instrument_index,
                name=name,
                fadeout=0,
                global_volume=128,
                panning=None,
                new_note_action=NewNoteAction.CUT,
                duplicate_check=DuplicateCheck.OFF,
                duplicate_action=DuplicateAction.CUT,
            )
        ]
    )


def test_instrument_names_by_hash_reports_the_voice_each_occurrence_is_reached_through(
    connection: Connection, stored_sample: Sample, stored_module: Module
) -> None:
    _add_occurrence(connection, sample=stored_sample, module=stored_module, slot=0, name="smp03")
    _add_instrument(connection, module=stored_module, instrument_index=0, name="warm pad")

    names = PostgresSampleRepository(connection).instrument_names_by_hash([stored_sample.hash])

    assert names == {stored_sample.hash: ("warm pad",)}


def test_instrument_names_by_hash_with_no_hashes_returns_nothing(connection: Connection) -> None:
    assert PostgresSampleRepository(connection).instrument_names_by_hash([]) == {}


def test_a_sample_is_categorized_by_the_name_of_the_voice_that_plays_it(
    connection: Connection, stored_sample: Sample, stored_module: Module
) -> None:
    """A waveform stored under a bare slot number is described only by the instrument reaching it."""
    _add_occurrence(connection, sample=stored_sample, module=stored_module, slot=0, name="smp03")
    _add_instrument(connection, module=stored_module, instrument_index=0, name="warm pad")

    page = PostgresSampleRepository(connection).list_page(limit=50, offset=0, class_by_hash={}, selection=EVERYTHING)

    assert page[0].display_name == "smp03"
    assert page[0].category is SampleCategory.PAD


def _annotate(
    connection: Connection,
    sample: Sample,
    *,
    rating: int | None = None,
    favorite: bool = False,
) -> None:
    PostgresSampleAnnotationRepository(connection).replace_many(
        (
            SampleAnnotation(
                sample_hash=sample.hash,
                label=None,
                rating=rating,
                favorite=favorite,
                occurrence=SampleOccurrence(module_hash=format(1, "064x"), instrument_index=0, sample_slot=0),
                module_filename="song.xm",
                sample_name="smp01",
                source=AnnotationSource.SAMPLE,
                annotated_at=datetime.now(UTC),
            ),
        )
    )


def test_list_page_narrowed_to_favorites_leaves_out_what_was_never_marked(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    """A favorite is rare and scattered, so narrowing has to reach the catalog, not just one page."""
    _annotate(connection, stored_sample, favorite=True)

    page = PostgresSampleRepository(connection).list_page(
        limit=50, offset=0, class_by_hash={}, selection=SampleSelection(favorites_only=True)
    )

    assert [summary.hash for summary in page] == [stored_sample.hash]


def test_a_narrowed_total_counts_what_the_page_walks(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    _annotate(connection, stored_sample, favorite=True)
    repository = PostgresSampleRepository(connection)

    assert repository.count(selection=SampleSelection(favorites_only=True)) == 1
    assert repository.count(selection=EVERYTHING) == 2


def test_list_page_narrowed_by_rating_keeps_only_what_reaches_the_floor(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    _annotate(connection, stored_sample, rating=4)
    _annotate(connection, stored_sample_b, rating=2)

    page = PostgresSampleRepository(connection).list_page(
        limit=50, offset=0, class_by_hash={}, selection=SampleSelection(minimum_rating=3)
    )

    assert [summary.hash for summary in page] == [stored_sample.hash]


def test_sorting_by_rating_puts_the_best_first_and_the_unrated_last(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    """Postgres places nulls first under DESC, which would open the listing with everything unrated."""
    unrated = Sample(hash="e" * 64, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
    PostgresSampleRepository(connection).upsert(unrated)
    _annotate(connection, stored_sample, rating=2)
    _annotate(connection, stored_sample_b, rating=5)

    page = PostgresSampleRepository(connection).list_page(
        limit=50, offset=0, class_by_hash={}, selection=SampleSelection(sort=SampleSort.RATING)
    )

    assert [summary.hash for summary in page] == [stored_sample_b.hash, stored_sample.hash, unrated.hash]


def test_successive_pages_under_a_rating_sort_stay_disjoint(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    """A rating takes five values across the whole catalog, so ties need a total order under them."""
    _annotate(connection, stored_sample, rating=3)
    _annotate(connection, stored_sample_b, rating=3)
    repository = PostgresSampleRepository(connection)
    selection = SampleSelection(sort=SampleSort.RATING)

    first = repository.list_page(limit=1, offset=0, class_by_hash={}, selection=selection)
    second = repository.list_page(limit=1, offset=1, class_by_hash={}, selection=selection)

    assert {summary.hash for summary in first}.isdisjoint({summary.hash for summary in second})


def _store_sized_sample(connection: Connection, *, index: int, frames: int) -> Sample:
    sample_ = Sample(hash=format(index, "064x"), depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=frames)
    PostgresSampleRepository(connection).upsert(sample_)
    connection.commit()
    return sample_


def test_sampling_reproducibly_returns_the_requested_count(connection: Connection) -> None:
    for index in range(10):
        _store_sized_sample(connection, index=index, frames=10_000)

    drawn = PostgresSampleRepository(connection).sample_reproducibly(
        count=4, random_seed=1, frame_floor=1_000, frame_ceiling=100_000
    )

    assert len(drawn) == 4


def test_sampling_reproducibly_repeats_its_draw_for_one_seed(connection: Connection) -> None:
    """A measurement re-run has to report on the same samples for its numbers to stay comparable."""
    for index in range(10):
        _store_sized_sample(connection, index=index, frames=10_000)
    repository = PostgresSampleRepository(connection)

    first = repository.sample_reproducibly(count=4, random_seed=1, frame_floor=1_000, frame_ceiling=100_000)
    second = repository.sample_reproducibly(count=4, random_seed=1, frame_floor=1_000, frame_ceiling=100_000)

    assert first == second


def test_sampling_reproducibly_draws_differently_under_a_different_seed(connection: Connection) -> None:
    for index in range(20):
        _store_sized_sample(connection, index=index, frames=10_000)
    repository = PostgresSampleRepository(connection)

    first = repository.sample_reproducibly(count=5, random_seed=1, frame_floor=1_000, frame_ceiling=100_000)
    second = repository.sample_reproducibly(count=5, random_seed=2, frame_floor=1_000, frame_ceiling=100_000)

    assert first != second


def test_sampling_reproducibly_keeps_to_the_frame_bounds(connection: Connection) -> None:
    _store_sized_sample(connection, index=1, frames=500)
    _store_sized_sample(connection, index=2, frames=10_000)
    _store_sized_sample(connection, index=3, frames=500_000)

    drawn = PostgresSampleRepository(connection).sample_reproducibly(
        count=10, random_seed=1, frame_floor=1_000, frame_ceiling=100_000
    )

    assert [sample_.frames for sample_ in drawn] == [10_000]
