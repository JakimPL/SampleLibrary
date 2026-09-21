from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any, Final, Protocol, TypeVar

from sqlalchemy import ColumnElement, Connection, Row, Select, func, select
from sqlalchemy.dialects.postgresql import insert
from trackmod.core.samples.depth import BitDepth
from trackmod.schema.scalars import Rate

from samplecore.digests import digest_of_rows
from samplecore.equivalence_classes import EquivalenceClass
from samplecore.models.annotation import SampleAnnotation
from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample, SampleSelection, SampleSort, SampleSummary
from samplecore.models.sample_file import stem_of
from samplecore.models.thumbnail import SampleThumbnail
from samplecore.naming import NO_DISPLAY_NAME, choose_dominant_name
from samplecore.pitch import choose_playback_rate
from samplecore.storage.curation import sample_annotation
from samplecore.storage.database import (
    HASH_CHUNK_SIZE,
    chunks,
    sample,
    sample_file,
    sample_properties,
)
from samplecore.storage.repositories.playback_rate import PostgresSamplePlaybackRateRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository
from samplecore.storage.repositories.sample_category import PostgresSampleCategoryRepository
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
        self,
        *,
        limit: int,
        offset: int,
        class_by_hash: dict[str, EquivalenceClass],
        selection: SampleSelection,
        shown_experiment_id: int | None,
    ) -> tuple[SampleSummary, ...]: ...

    def count(self, *, selection: SampleSelection) -> int: ...

    def display_names_and_rates_by_hash(
        self, hashes: list[str]
    ) -> tuple[dict[str, str], dict[str, tuple[Rate, ...]]]: ...

    def rates_by_hash(self, hashes: list[str]) -> dict[str, tuple[Rate, ...]]: ...

    def rates_for_every_sample(self) -> dict[str, tuple[Rate, ...]]: ...


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
        """Every cataloged sample in hash order, so a pass over the first N reaches the same N each run."""
        rows = self._connection.execute(select(sample).order_by(sample.c.hash)).fetchall()
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

    # The page is assembled from one row query and the by-hash lookups that fill it out, each an
    # independent source with nothing to group them under.
    # pylint: disable-next=too-many-locals
    def list_page(
        self,
        *,
        limit: int,
        offset: int,
        class_by_hash: dict[str, EquivalenceClass],
        selection: SampleSelection,
        shown_experiment_id: int | None,
    ) -> tuple[SampleSummary, ...]:
        """A page of samples, one row per exact content hash, in the order ``selection`` asks for.

        ``class_by_hash`` supplies each row's equivalence class, when it has one, so that the
        badge it renders reflects the whole catalog's relation graph rather than only this page.
        Collapsing same-page rows that share a class into one representative is the caller's own
        concern, not this method's -- it always returns one row per hash.

        ``selection`` narrows and orders the page through the annotation a person made, joined
        here rather than filtered afterwards: a favorite is rare and scattered, so a page walked
        over the whole catalog would hold almost none of them.

        ``shown_experiment_id`` names the scoring whose top categories fill each row's category,
        resolved once by the caller; with no scoring on show every row carries none.
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
        display_names, rates_by_hash = self.display_names_and_rates_by_hash(hashes)
        playback_rate_by_hash = PostgresSamplePlaybackRateRepository(self._connection).get_many(hashes)
        thumbnails_by_hash = PostgresSampleThumbnailRepository(self._connection).get_many(hashes)
        annotation_by_hash = PostgresSampleAnnotationRepository(self._connection).annotations_by_hash(hashes)
        top_category_by_hash = (
            {}
            if shown_experiment_id is None
            else PostgresSampleCategoryRepository(self._connection).top_category_labels(shown_experiment_id, hashes)
        )
        return tuple(
            _row_to_sample_summary(
                row,
                display_name=display_names.get(row.hash, NO_DISPLAY_NAME),
                rates=rates_by_hash.get(row.hash, ()),
                recorded_playback_rate=playback_rate_by_hash.get(row.hash),
                thumbnail=thumbnails_by_hash.get(row.hash),
                equivalence_class=class_by_hash.get(row.hash),
                annotation=annotation_by_hash.get(row.hash),
                category=top_category_by_hash.get(row.hash),
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

    def display_names_and_rates_by_hash(self, hashes: list[str]) -> tuple[dict[str, str], dict[str, tuple[Rate, ...]]]:
        """The name each given sample is shown by, and every rate it is declared at, in chunked queries.

        Both come from each module occurrence and each sample file; a sample neither names is left
        out of the names. Chunked by ``HASH_CHUNK_SIZE`` so each lookup stays within Postgres's own
        parameter ceiling, which a page of any size stays comfortably inside.
        """
        return _display_names_and_rates_of(
            occurrences=self._chunked(_OCCURRENCE_NAMES_AND_RATES, sample_properties.c.sample_hash, hashes),
            files=self._chunked(_FILE_PATHS_AND_RATES, sample_file.c.sample_hash, hashes),
        )

    def rates_by_hash(self, hashes: list[str]) -> dict[str, tuple[Rate, ...]]:
        """Every rate each given sample is declared at, by its module occurrences and its sample files."""
        return _rates_of(
            self._chunked(_OCCURRENCE_NAMES_AND_RATES, sample_properties.c.sample_hash, hashes),
            self._chunked(_FILE_PATHS_AND_RATES, sample_file.c.sample_hash, hashes),
        )

    def rates_for_every_sample(self) -> dict[str, tuple[Rate, ...]]:
        """The same, for the whole catalog, in one scan of the occurrences and one of the sample files."""
        return _rates_of(
            self._connection.execute(_OCCURRENCE_NAMES_AND_RATES).fetchall(),
            self._connection.execute(_FILE_PATHS_AND_RATES).fetchall(),
        )

    def _chunked(self, statement: Select[Any], hash_column: ColumnElement[str], hashes: list[str]) -> list[Row[Any]]:
        """Every row ``statement`` reaches for ``hashes``, asked for in parameter-sized chunks."""
        rows: list[Row[Any]] = []
        for chunk in chunks(hashes, HASH_CHUNK_SIZE):
            rows.extend(self._connection.execute(statement.where(hash_column.in_(chunk))).fetchall())

        return rows

    def membership_digest(self) -> str:
        """One digest over every cataloged sample's hash, so a pass reading the catalog can tell whether the set moved."""
        rows = self._connection.execute(select(sample.c.hash).order_by(sample.c.hash)).scalars()
        return digest_of_rows((str(sample_hash),) for sample_hash in rows)

    def hashes_held_by_modules(self) -> frozenset[str]:
        """Every sample a module occurrence holds, which is the part of the catalog the tracker modules supply."""
        rows = self._connection.execute(select(sample_properties.c.sample_hash).distinct()).scalars()
        return frozenset(str(sample_hash) for sample_hash in rows)


_OCCURRENCE_NAMES_AND_RATES: Final[Select[Any]] = select(
    sample_properties.c.sample_hash, sample_properties.c.name, sample_properties.c.rate
)

_FILE_PATHS_AND_RATES: Final[Select[Any]] = select(
    sample_file.c.sample_hash, sample_file.c.relative_path, sample_file.c.rate
).order_by(sample_file.c.directory, sample_file.c.relative_path)


def _display_names_and_rates_of(
    *, occurrences: Sequence[Row[Any]], files: Sequence[Row[Any]]
) -> tuple[dict[str, str], dict[str, tuple[Rate, ...]]]:
    """Gather occurrence and file rows into the name each sample hash is shown by and the rates it is declared at."""
    own_names: dict[str, list[str]] = defaultdict(list)
    for row in occurrences:
        own_names[row.sample_hash].append(row.name)
    for row in files:
        own_names[row.sample_hash].append(stem_of(row.relative_path))

    display_names = {sample_hash: choose_dominant_name(names) for sample_hash, names in own_names.items()}
    return display_names, _rates_of(occurrences, files)


def _rates_of(occurrences: Sequence[Row[Any]], files: Sequence[Row[Any]]) -> dict[str, tuple[Rate, ...]]:
    """Gather rate-carrying rows into the rates each sample hash is declared at."""
    rates_by_hash: dict[str, list[Rate]] = defaultdict(list)
    for row in (*occurrences, *files):
        rates_by_hash[row.sample_hash].append(row.rate)

    return {hash_: tuple(rates) for hash_, rates in rates_by_hash.items()}


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
    display_name: str,
    rates: tuple[Rate, ...],
    recorded_playback_rate: Rate | None,
    thumbnail: SampleThumbnail | None,
    equivalence_class: EquivalenceClass | None,
    annotation: SampleAnnotation | None,
    category: str | None,
) -> SampleSummary:
    """Reconstruct a SampleSummary from a Core row plus its display name and rates, thumbnail, and class.

    The display name is drawn from the names the waveform itself is stored under, keeping it the
    label a tracker or a file shows. It stays filled in beside what a person decided and what a
    listening model heard, so a reader meets every reading of the sample at once.
    """
    sample_ = _row_to_sample(row)
    return SampleSummary(
        hash=sample_.hash,
        depth=sample_.depth,
        channels=sample_.channels,
        frames=sample_.frames,
        occurrence_count=row.occurrence_count,
        display_name=display_name,
        category=category,
        size_bytes=sample_.stored_bytes,
        thumbnail=peaks_from_thumbnail(thumbnail),
        playback_rate_hz=choose_playback_rate(note_event_rate=recorded_playback_rate, occurrence_rates=rates),
        equivalence_class_hash=equivalence_class.class_hash if equivalence_class is not None else None,
        equivalence_member_count=len(equivalence_class.member_hashes) if equivalence_class is not None else 1,
        hand_label=annotation.label if annotation is not None else None,
        rating=annotation.rating if annotation is not None else None,
        favorite=annotation.favorite if annotation is not None else False,
    )
