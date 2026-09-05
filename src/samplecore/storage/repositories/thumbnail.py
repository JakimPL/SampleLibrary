from __future__ import annotations

from typing import Protocol

from sqlalchemy import Connection, Row, select
from sqlalchemy.dialects.postgresql import insert

from samplecore.models.thumbnail import SampleThumbnail
from samplecore.storage.database import sample_thumbnail
from samplecore.waveform import WaveformPeak


class SampleThumbnailRepository(Protocol):
    """Persistence for a Sample's cached, low-resolution waveform preview."""

    def upsert(self, thumbnail: SampleThumbnail) -> None: ...

    def get(self, sample_hash: str) -> SampleThumbnail | None: ...

    def get_many(self, sample_hashes: list[str]) -> dict[str, SampleThumbnail]: ...


class DuckDBSampleThumbnailRepository:
    """A SampleThumbnailRepository backed by the catalog's ``sample_thumbnail`` table.

    ``upsert`` replaces a sample's thumbnail outright: a resolution change or a re-render always
    supersedes whatever was cached before, the same replace-on-conflict semantics
    ``CloudCoordinateRepository`` uses for its own recomputed-per-run artifact.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def upsert(self, thumbnail: SampleThumbnail) -> None:
        statement = insert(sample_thumbnail).values(
            sample_hash=thumbnail.sample_hash,
            bucket_count=thumbnail.bucket_count,
            minimums=list(thumbnail.minimums),
            maximums=list(thumbnail.maximums),
        )
        statement = statement.on_conflict_do_update(
            index_elements=[sample_thumbnail.c.sample_hash],
            set_={
                "bucket_count": statement.excluded.bucket_count,
                "minimums": statement.excluded.minimums,
                "maximums": statement.excluded.maximums,
            },
        )
        self._connection.execute(statement)

    def get(self, sample_hash: str) -> SampleThumbnail | None:
        row = self._connection.execute(
            select(sample_thumbnail).where(sample_thumbnail.c.sample_hash == sample_hash)
        ).fetchone()
        return _row_to_thumbnail(row) if row is not None else None

    def get_many(self, sample_hashes: list[str]) -> dict[str, SampleThumbnail]:
        if not sample_hashes:
            return {}

        statement = select(sample_thumbnail).where(sample_thumbnail.c.sample_hash.in_(sample_hashes))
        rows = self._connection.execute(statement).fetchall()
        return {row.sample_hash: _row_to_thumbnail(row) for row in rows}


def _row_to_thumbnail(row: Row[tuple[str, int, list[float], list[float]]]) -> SampleThumbnail:
    """Reconstruct a SampleThumbnail from a Core row, addressed by its own column names."""
    return SampleThumbnail(
        sample_hash=row.sample_hash,
        bucket_count=row.bucket_count,
        minimums=tuple(row.minimums),
        maximums=tuple(row.maximums),
    )


def peaks_from_thumbnail(thumbnail: SampleThumbnail | None) -> tuple[WaveformPeak, ...] | None:
    """A cached SampleThumbnail's buckets, reshaped into the same WaveformPeak shape a live
    waveform preview uses, so both share one representation on the wire. `None` in, `None` out --
    a sample with no cached thumbnail yet has no preview to show.
    """
    if thumbnail is None:
        return None

    return tuple(
        WaveformPeak(minimum=minimum, maximum=maximum)
        for minimum, maximum in zip(thumbnail.minimums, thumbnail.maximums, strict=True)
    )
