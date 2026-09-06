from __future__ import annotations

from collections import defaultdict
from typing import Any, Protocol

from sqlalchemy import Connection, Row, func, select
from sqlalchemy.dialects.postgresql import insert
from trackmod.core.samples.depth import BitDepth
from trackmod.schema.scalars import Rate

from samplecore.equivalence_classes import EquivalenceClass
from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample, SampleSummary
from samplecore.models.thumbnail import SampleThumbnail
from samplecore.naming import choose_dominant_name, choose_dominant_rate
from samplecore.storage.database import sample, sample_properties
from samplecore.storage.repositories.thumbnail import DuckDBSampleThumbnailRepository, peaks_from_thumbnail


class SampleRepository(Protocol):
    """Persistence for the Sample catalog: the content-addressed identity of extracted waveforms."""

    def get(self, hash_: str) -> Sample | None: ...

    def get_many(self, hashes: list[str]) -> dict[str, Sample]: ...

    def upsert(self, sample_: Sample) -> None: ...

    def list_all(self) -> tuple[Sample, ...]: ...

    def list_page(
        self, *, limit: int, offset: int, class_by_hash: dict[str, EquivalenceClass]
    ) -> tuple[SampleSummary, ...]: ...

    def count(self) -> int: ...


class DuckDBSampleRepository:
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

    def list_page(
        self, *, limit: int, offset: int, class_by_hash: dict[str, EquivalenceClass]
    ) -> tuple[SampleSummary, ...]:
        """A page of samples ranked by identity: one row per exact content hash, most-occurring first.

        ``class_by_hash`` supplies each row's equivalence class, when it has one, so that the
        badge it renders reflects the whole catalog's relation graph rather than only this page.
        Collapsing same-page rows that share a class into one representative is the caller's own
        concern, not this method's -- it always returns one row per hash.
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
            .order_by(occurrence_count.desc(), sample.c.hash.asc())
            .limit(limit)
            .offset(offset)
        )
        rows = self._connection.execute(statement).fetchall()
        hashes = [row.hash for row in rows]
        names_by_hash, rates_by_hash = self._names_and_rates_by_sample_hash(hashes)
        thumbnails_by_hash = DuckDBSampleThumbnailRepository(self._connection).get_many(hashes)
        return tuple(
            _row_to_sample_summary(
                row,
                names_by_hash.get(row.hash, ()),
                rates_by_hash.get(row.hash, ()),
                thumbnails_by_hash.get(row.hash),
                class_by_hash.get(row.hash),
            )
            for row in rows
        )

    def count(self) -> int:
        # pylint: disable-next=not-callable
        return self._connection.execute(select(func.count()).select_from(sample)).scalar_one()

    def _names_and_rates_by_sample_hash(
        self, hashes: list[str]
    ) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[Rate, ...]]]:
        """Every occurrence's raw name and rate for each given sample hash, in one batched query."""
        names_by_hash: dict[str, list[str]] = defaultdict(list)
        rates_by_hash: dict[str, list[Rate]] = defaultdict(list)
        if not hashes:
            return {}, {}

        statement = select(sample_properties.c.sample_hash, sample_properties.c.name, sample_properties.c.rate).where(
            sample_properties.c.sample_hash.in_(hashes)
        )
        for row in self._connection.execute(statement).fetchall():
            names_by_hash[row.sample_hash].append(row.name)
            rates_by_hash[row.sample_hash].append(row.rate)

        return (
            {hash_: tuple(names) for hash_, names in names_by_hash.items()},
            {hash_: tuple(rates) for hash_, rates in rates_by_hash.items()},
        )


def _row_to_sample(row: Row[Any]) -> Sample:
    """Reconstruct a Sample from a Core row, addressed by its own column names."""
    return Sample(hash=row.hash, depth=BitDepth(row.depth), channels=ChannelLayout(row.channels), frames=row.frames)


def _row_to_sample_summary(
    row: Row[Any],
    names: tuple[str, ...],
    rates: tuple[Rate, ...],
    thumbnail: SampleThumbnail | None,
    equivalence_class: EquivalenceClass | None,
) -> SampleSummary:
    """Reconstruct a SampleSummary from a Core row plus its occurrences' raw names/rates, thumbnail, and class."""
    sample_ = _row_to_sample(row)
    return SampleSummary(
        hash=sample_.hash,
        depth=sample_.depth,
        channels=sample_.channels,
        frames=sample_.frames,
        occurrence_count=row.occurrence_count,
        display_name=choose_dominant_name(names),
        size_bytes=sample_.stored_bytes,
        thumbnail=peaks_from_thumbnail(thumbnail),
        dominant_rate_hz=choose_dominant_rate(rates),
        equivalence_class_hash=equivalence_class.class_hash if equivalence_class is not None else None,
        equivalence_member_count=len(equivalence_class.member_hashes) if equivalence_class is not None else 1,
    )
