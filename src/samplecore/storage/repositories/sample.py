from __future__ import annotations

from collections import defaultdict
from typing import Any, Protocol, TypeVar

from sqlalchemy import ColumnElement, Connection, Row, Select, func, select
from sqlalchemy.dialects.postgresql import insert
from trackmod.core.samples.depth import BitDepth
from trackmod.schema.scalars import Rate

from samplecore.categorization import classify_sample_category
from samplecore.equivalence_classes import EquivalenceClass
from samplecore.models.annotation import SampleAnnotation
from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample, SampleSelection, SampleSort, SampleSummary
from samplecore.models.thumbnail import SampleThumbnail
from samplecore.naming import choose_dominant_name
from samplecore.pitch import choose_playback_rate
from samplecore.storage.curation import sample_annotation
from samplecore.storage.database import HASH_CHUNK_SIZE, module_instrument, sample, sample_properties
from samplecore.storage.repositories.playback_rate import PostgresSamplePlaybackRateRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository
from samplecore.storage.repositories.thumbnail import PostgresSampleThumbnailRepository, peaks_from_thumbnail

_SelectT = TypeVar("_SelectT", bound=Select[Any])


class SampleRepository(Protocol):
    """Persistence for the Sample catalog: the content-addressed identity of extracted waveforms."""

    def get(self, hash_: str) -> Sample | None: ...

    def get_many(self, hashes: list[str]) -> dict[str, Sample]: ...

    def upsert(self, sample_: Sample) -> None: ...

    def list_all(self) -> tuple[Sample, ...]: ...

    def sample_reproducibly(
        self, *, count: int, random_seed: int, frame_floor: int, frame_ceiling: int
    ) -> tuple[Sample, ...]: ...

    def list_page(
        self, *, limit: int, offset: int, class_by_hash: dict[str, EquivalenceClass], selection: SampleSelection
    ) -> tuple[SampleSummary, ...]: ...

    def count(self, *, selection: SampleSelection) -> int: ...

    def names_and_rates_by_hash(
        self, hashes: list[str]
    ) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[Rate, ...]]]: ...

    def instrument_names_by_hash(self, hashes: list[str]) -> dict[str, tuple[str, ...]]: ...


class PostgresSampleRepository:
    """A SampleRepository backed by the catalog's ``sample`` table.

    ``upsert`` is idempotent-insert, not a true update: a Sample's fields are fully determined by
    its own hash, so a second call for a hash already on file can only ever repeat the same row.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get(self, hash_: str) -> Sample | None:
        row = self._connection.execute(select(sample).where(sample.c.hash == hash_)).fetchone()
        return _row_to_sample(row) if row is not None else None

    def get_many(self, hashes: list[str]) -> dict[str, Sample]:
        if not hashes:
            return {}

        statement = select(sample).where(sample.c.hash.in_(hashes))
        rows = self._connection.execute(statement).fetchall()
        return {row.hash: _row_to_sample(row) for row in rows}

    def upsert(self, sample_: Sample) -> None:
        statement = insert(sample).values(
            hash=sample_.hash, depth=sample_.depth.value, channels=sample_.channels.value, frames=sample_.frames
        )
        statement = statement.on_conflict_do_nothing(index_elements=[sample.c.hash])
        self._connection.execute(statement)

    def list_all(self) -> tuple[Sample, ...]:
        rows = self._connection.execute(select(sample)).fetchall()
        return tuple(_row_to_sample(row) for row in rows)

    def sample_reproducibly(
        self, *, count: int, random_seed: int, frame_floor: int, frame_ceiling: int
    ) -> tuple[Sample, ...]:
        """Up to `count` samples of a length between the two bounds, drawn the same way every run.

        Ordering by a digest of each hash together with `random_seed` gives one fixed draw per
        seed, so a measurement re-run reports on the same samples and its numbers stay comparable
        across runs. Sorting in the database keeps the whole catalog available to the draw without
        reading it into memory first.
        """
        statement = (
            select(sample)
            .where(sample.c.frames.between(frame_floor, frame_ceiling))
            .order_by(func.md5(sample.c.hash + str(random_seed)))
            .limit(count)
        )
        rows = self._connection.execute(statement).fetchall()
        return tuple(_row_to_sample(row) for row in rows)

    def list_page(
        self, *, limit: int, offset: int, class_by_hash: dict[str, EquivalenceClass], selection: SampleSelection
    ) -> tuple[SampleSummary, ...]:
        """A page of samples, one row per exact content hash, in the order ``selection`` asks for.

        ``class_by_hash`` supplies each row's equivalence class, when it has one, so that the
        badge it renders reflects the whole catalog's relation graph rather than only this page.
        Collapsing same-page rows that share a class into one representative is the caller's own
        concern, not this method's -- it always returns one row per hash.

        ``selection`` narrows and orders the page through the annotation a person made, joined
        here rather than filtered afterwards: a favorite is rare and scattered, so a page walked
        over the whole catalog would hold almost none of them.
        """
        # func.count()/func.coalesce() are SQLAlchemy's dynamically-generated SQL functions, invisible
        # to pylint's static analysis -- both false positives below are this same proxy limitation.
        occurrence_counts = (
            # pylint: disable-next=not-callable
            select(sample_properties.c.sample_hash, func.count().label("occurrence_count"))
            .group_by(sample_properties.c.sample_hash)
            .subquery()
        )
        # pylint: disable-next=assignment-from-no-return
        occurrence_count = func.coalesce(occurrence_counts.c.occurrence_count, 0)
        statement = (
            select(
                sample.c.hash,
                sample.c.depth,
                sample.c.channels,
                sample.c.frames,
                occurrence_count.label("occurrence_count"),
            )
            .select_from(sample.outerjoin(occurrence_counts, occurrence_counts.c.sample_hash == sample.c.hash))
            .order_by(*_order_by(selection.sort, occurrence_count))
            .limit(limit)
            .offset(offset)
        )
        rows = self._connection.execute(_with_selection(statement, selection)).fetchall()
        hashes = [row.hash for row in rows]
        names_by_hash, rates_by_hash = self.names_and_rates_by_hash(hashes)
        instrument_names_by_hash = self.instrument_names_by_hash(hashes)
        playback_rate_by_hash = PostgresSamplePlaybackRateRepository(self._connection).get_many(hashes)
        thumbnails_by_hash = PostgresSampleThumbnailRepository(self._connection).get_many(hashes)
        annotation_by_hash = PostgresSampleAnnotationRepository(self._connection).annotations_by_hash(hashes)
        return tuple(
            _row_to_sample_summary(
                row,
                names=names_by_hash.get(row.hash, ()),
                instrument_names=instrument_names_by_hash.get(row.hash, ()),
                rates=rates_by_hash.get(row.hash, ()),
                recorded_playback_rate=playback_rate_by_hash.get(row.hash),
                thumbnail=thumbnails_by_hash.get(row.hash),
                equivalence_class=class_by_hash.get(row.hash),
                annotation=annotation_by_hash.get(row.hash),
            )
            for row in rows
        )

    def count(self, *, selection: SampleSelection) -> int:
        """How many samples ``list_page`` walks, so a page total matches what it lists.

        Only the narrowing half of ``selection`` applies: an order cannot change how many rows
        there are, and sorting a count would be work for nothing.
        """
        # pylint: disable-next=not-callable
        statement = select(func.count()).select_from(sample)
        return self._connection.execute(_with_selection(statement, selection)).scalar_one()

    def names_and_rates_by_hash(
        self, hashes: list[str]
    ) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[Rate, ...]]]:
        """Every occurrence's raw name and rate for each given sample hash, in chunked queries.

        Chunked by ``HASH_CHUNK_SIZE`` so a whole-catalog lookup stays within Postgres's own
        parameter ceiling, which a library of this size passes.
        """
        names_by_hash: dict[str, list[str]] = defaultdict(list)
        rates_by_hash: dict[str, list[Rate]] = defaultdict(list)

        for chunk_start in range(0, len(hashes), HASH_CHUNK_SIZE):
            chunk = hashes[chunk_start : chunk_start + HASH_CHUNK_SIZE]
            statement = select(
                sample_properties.c.sample_hash, sample_properties.c.name, sample_properties.c.rate
            ).where(sample_properties.c.sample_hash.in_(chunk))
            for row in self._connection.execute(statement).fetchall():
                names_by_hash[row.sample_hash].append(row.name)
                rates_by_hash[row.sample_hash].append(row.rate)

        return (
            {hash_: tuple(names) for hash_, names in names_by_hash.items()},
            {hash_: tuple(rates) for hash_, rates in rates_by_hash.items()},
        )

    def instrument_names_by_hash(self, hashes: list[str]) -> dict[str, tuple[str, ...]]:
        """The name of every instrument slot each given sample is reached through, in chunked queries.

        A tracker names an instrument apart from the waveforms its keys reach, so these carry
        description a sample's own name leaves out -- a waveform stored as "smp03" reached through an
        instrument called "warm pad" says what it is only here. Chunked by ``HASH_CHUNK_SIZE``, the
        same way occurrence names are, so a whole-catalog lookup stays inside Postgres's parameter
        ceiling.
        """
        names_by_hash: dict[str, list[str]] = defaultdict(list)

        for chunk_start in range(0, len(hashes), HASH_CHUNK_SIZE):
            chunk = hashes[chunk_start : chunk_start + HASH_CHUNK_SIZE]
            statement = (
                select(sample_properties.c.sample_hash, module_instrument.c.name)
                .select_from(
                    sample_properties.join(
                        module_instrument,
                        (module_instrument.c.module_id == sample_properties.c.module_id)
                        & (module_instrument.c.instrument_index == sample_properties.c.instrument_index),
                    )
                )
                .where(sample_properties.c.sample_hash.in_(chunk))
                .where(module_instrument.c.name != "")
            )
            for row in self._connection.execute(statement).fetchall():
                names_by_hash[row.sample_hash].append(row.name)

        return {hash_: tuple(names) for hash_, names in names_by_hash.items()}


def _row_to_sample(row: Row[Any]) -> Sample:
    """Reconstruct a Sample from a Core row, addressed by its own column names."""
    return Sample(hash=row.hash, depth=BitDepth(row.depth), channels=ChannelLayout(row.channels), frames=row.frames)


def _with_selection(statement: _SelectT, selection: SampleSelection) -> _SelectT:
    """Attach each sample's hand annotation and narrow the statement to what ``selection`` asks for.

    ``sample_hash`` is the annotation table's primary key, so this join is one-to-at-most-one and
    leaves the row count alone -- which is what lets ``count`` reuse it and still agree with the page
    ``list_page`` returns. The annotations live in a schema of their own, on their own metadata, and
    a single SELECT reaches across both because they share one database.
    """
    statement = statement.outerjoin(sample_annotation, sample_annotation.c.sample_hash == sample.c.hash)
    if selection.favorites_only:
        statement = statement.where(sample_annotation.c.favorite.is_(True))
    if selection.minimum_rating is not None:
        statement = statement.where(sample_annotation.c.rating >= selection.minimum_rating)

    return statement


def _order_by(sort: SampleSort, occurrence_count: ColumnElement[int]) -> tuple[ColumnElement[Any], ...]:
    """The ordering for one sort, always ending in the hash so successive pages stay disjoint.

    A listing is walked by offset, and a rating takes one of five values across the whole catalog,
    so ties are enormous; a total order is what keeps a later page from repeating and dropping rows.
    Rating orders highest first with the unrated last, Postgres placing nulls first under ``DESC``
    otherwise -- which would open the listing with every sample nobody has rated.
    """
    match sort:
        case SampleSort.OCCURRENCES:
            return (occurrence_count.desc(), sample.c.hash.asc())
        case SampleSort.RATING:
            return (sample_annotation.c.rating.desc().nulls_last(), occurrence_count.desc(), sample.c.hash.asc())


# Every keyword below is an independent lookup resolved for this one row, with no natural
# subgrouping short of a wrapper this function would be the only caller of.
# pylint: disable-next=too-many-arguments
def _row_to_sample_summary(
    row: Row[Any],
    *,
    names: tuple[str, ...],
    instrument_names: tuple[str, ...],
    rates: tuple[Rate, ...],
    recorded_playback_rate: Rate | None,
    thumbnail: SampleThumbnail | None,
    equivalence_class: EquivalenceClass | None,
    annotation: SampleAnnotation | None,
) -> SampleSummary:
    """Reconstruct a SampleSummary from a Core row plus its occurrences' names/rates, thumbnail, and class.

    The display name is drawn from the sample's own occurrence names, keeping it the label a tracker
    shows, while the category reads the instrument names too, since a voice is often described where
    the waveform it reaches is only numbered. Both stay filled in beside what a person decided, so a
    reader sees their own wording next to what the keyword table guessed.
    """
    sample_ = _row_to_sample(row)
    return SampleSummary(
        hash=sample_.hash,
        depth=sample_.depth,
        channels=sample_.channels,
        frames=sample_.frames,
        occurrence_count=row.occurrence_count,
        display_name=choose_dominant_name(names),
        category=classify_sample_category(names + instrument_names),
        size_bytes=sample_.stored_bytes,
        thumbnail=peaks_from_thumbnail(thumbnail),
        playback_rate_hz=choose_playback_rate(note_event_rate=recorded_playback_rate, occurrence_rates=rates),
        equivalence_class_hash=equivalence_class.class_hash if equivalence_class is not None else None,
        equivalence_member_count=len(equivalence_class.member_hashes) if equivalence_class is not None else 1,
        hand_label=annotation.label if annotation is not None else None,
        rating=annotation.rating if annotation is not None else None,
        favorite=annotation.favorite if annotation is not None else False,
    )
