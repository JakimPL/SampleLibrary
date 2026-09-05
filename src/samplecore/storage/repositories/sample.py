from __future__ import annotations

from collections import defaultdict
from typing import Any, Protocol

import duckdb
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample, SampleSummary
from samplecore.naming import choose_dominant_name


class SampleRepository(Protocol):
    """Persistence for the Sample catalog: the content-addressed identity of extracted waveforms."""

    def get(self, hash_: str) -> Sample | None: ...

    def upsert(self, sample: Sample) -> None: ...

    def list_all(self) -> tuple[Sample, ...]: ...

    def list_page(self, *, limit: int, offset: int) -> tuple[SampleSummary, ...]: ...

    def count(self) -> int: ...


class DuckDBSampleRepository:
    """A SampleRepository backed by the catalog's ``sample`` table.

    ``upsert`` is idempotent-insert, not a true update: a Sample's fields are fully determined by
    its own hash, so a second call for a hash already on file can only ever repeat the same row.
    """

    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._connection = connection

    def get(self, hash_: str) -> Sample | None:
        row = self._connection.execute(
            "SELECT hash, depth, channels, frames FROM sample WHERE hash = ?", [hash_]
        ).fetchone()
        return _row_to_sample(row) if row is not None else None

    def upsert(self, sample: Sample) -> None:
        self._connection.execute(
            """
            INSERT INTO sample (hash, depth, channels, frames)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (hash) DO NOTHING
            """,
            [sample.hash, sample.depth.value, sample.channels.value, sample.frames],
        )

    def list_all(self) -> tuple[Sample, ...]:
        rows = self._connection.execute("SELECT hash, depth, channels, frames FROM sample").fetchall()
        return tuple(_row_to_sample(row) for row in rows)

    def list_page(self, *, limit: int, offset: int) -> tuple[SampleSummary, ...]:
        """A page of samples ranked by identity: one row per exact content hash, most-occurring first.

        Ranking by equivalence class -- one row per group of near-duplicate variants -- is a
        distinct future method, not a hidden mode of this one.
        """
        rows = self._connection.execute(
            """
            SELECT sample.hash, sample.depth, sample.channels, sample.frames,
                   coalesce(occurrence_counts.occurrence_count, 0) AS occurrence_count
            FROM sample
            LEFT JOIN (
                SELECT sample_hash, count(*) AS occurrence_count
                FROM sample_properties
                GROUP BY sample_hash
            ) occurrence_counts ON occurrence_counts.sample_hash = sample.hash
            ORDER BY occurrence_count DESC, sample.hash ASC
            LIMIT ? OFFSET ?
            """,
            [limit, offset],
        ).fetchall()
        names_by_hash = self._names_by_sample_hash([row[0] for row in rows])
        return tuple(_row_to_sample_summary(row, names_by_hash.get(row[0], ())) for row in rows)

    def count(self) -> int:
        row = self._connection.execute("SELECT count(*) FROM sample").fetchone()
        assert row is not None
        return int(row[0])

    def _names_by_sample_hash(self, hashes: list[str]) -> dict[str, tuple[str, ...]]:
        names_by_hash: dict[str, list[str]] = defaultdict(list)
        if not hashes:
            return {}

        placeholders = ", ".join("?" for _ in hashes)
        rows = self._connection.execute(
            f"SELECT sample_hash, name FROM sample_properties WHERE sample_hash IN ({placeholders})", hashes
        ).fetchall()
        for sample_hash, name in rows:
            names_by_hash[sample_hash].append(name)

        return {hash_: tuple(names) for hash_, names in names_by_hash.items()}


def _row_to_sample(row: tuple[Any, ...]) -> Sample:
    """Reconstruct a Sample from a raw DuckDB row, an untyped boundary whose column order is fixed above."""
    hash_, depth, channels, frames = row
    return Sample(hash=hash_, depth=BitDepth(depth), channels=ChannelLayout(channels), frames=frames)


def _row_to_sample_summary(row: tuple[Any, ...], names: tuple[str, ...]) -> SampleSummary:
    """Reconstruct a SampleSummary from a raw DuckDB row plus its occurrences' raw names."""
    hash_, depth, channels, frames, occurrence_count = row
    sample = Sample(hash=hash_, depth=BitDepth(depth), channels=ChannelLayout(channels), frames=frames)
    return SampleSummary(
        hash=sample.hash,
        depth=sample.depth,
        channels=sample.channels,
        frames=sample.frames,
        occurrence_count=occurrence_count,
        display_name=choose_dominant_name(names),
        size_bytes=sample.stored_bytes,
    )
