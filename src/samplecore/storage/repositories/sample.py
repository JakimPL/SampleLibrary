from __future__ import annotations

from typing import Any, Protocol

import duckdb
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample


class SampleRepository(Protocol):
    """Persistence for the Sample catalog: the content-addressed identity of extracted waveforms."""

    def get(self, hash_: str) -> Sample | None: ...

    def upsert(self, sample: Sample) -> None: ...

    def list_all(self) -> tuple[Sample, ...]: ...


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


def _row_to_sample(row: tuple[Any, ...]) -> Sample:
    """Reconstruct a Sample from a raw DuckDB row, an untyped boundary whose column order is fixed above."""
    hash_, depth, channels, frames = row
    return Sample(hash=hash_, depth=BitDepth(depth), channels=ChannelLayout(channels), frames=frames)
