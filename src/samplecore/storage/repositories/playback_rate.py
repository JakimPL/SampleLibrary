from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Protocol

from sqlalchemy import Connection, select
from trackmod.schema.scalars import Rate

from samplecore.storage.database import HASH_CHUNK_SIZE, bulk_insert, sample_playback_rate

_COLUMN_NAMES: Final[tuple[str, ...]] = ("sample_hash", "rate")


class SamplePlaybackRateRepository(Protocol):
    """Persistence for the effective rate each sample's note events settle on."""

    def replace_all(self, rate_by_hash: Mapping[str, Rate]) -> None: ...

    def get_many(self, sample_hashes: list[str]) -> dict[str, Rate]: ...

    def list_all(self) -> dict[str, Rate]: ...


class PostgresSamplePlaybackRateRepository:
    """A SamplePlaybackRateRepository backed by the catalog's ``sample_playback_rate`` table.

    The rates are one whole-catalog aggregate taken in a single pass, so ``replace_all`` writes the
    whole answer at once: a sample whose note events have gone leaves with them, and every rate on
    file comes from the same reading of the catalog. A sample missing from the table is one no
    pattern plays, which a reader answers from its occurrences instead.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def replace_all(self, rate_by_hash: Mapping[str, Rate]) -> None:
        self._connection.execute(sample_playback_rate.delete())
        if not rate_by_hash:
            return

        bulk_insert(self._connection, sample_playback_rate, _COLUMN_NAMES, rate_by_hash.items())

    def get_many(self, sample_hashes: list[str]) -> dict[str, Rate]:
        """The recorded rate of each given sample, in chunked queries, leaving out those with none.

        Chunked by ``HASH_CHUNK_SIZE`` so a whole-catalog lookup stays within Postgres's own
        parameter ceiling, the same way every other by-hash lookup does.
        """
        rate_by_hash: dict[str, Rate] = {}
        for chunk_start in range(0, len(sample_hashes), HASH_CHUNK_SIZE):
            chunk = sample_hashes[chunk_start : chunk_start + HASH_CHUNK_SIZE]
            statement = select(sample_playback_rate).where(sample_playback_rate.c.sample_hash.in_(chunk))
            rate_by_hash.update({row.sample_hash: row.rate for row in self._connection.execute(statement)})

        return rate_by_hash

    def list_all(self) -> dict[str, Rate]:
        """Every recorded rate at once, which is what a whole-catalog view needs to sound a click."""
        return {row.sample_hash: row.rate for row in self._connection.execute(select(sample_playback_rate))}
