from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Protocol

from sqlalchemy import Connection, String, cast, func, select
from trackmod.schema.scalars import Rate

from samplecore.digests import digest_of_rows
from samplecore.storage.database import HASH_CHUNK_SIZE, bulk_insert, chunks, sample_playback_rate

_COLUMN_NAMES: Final[tuple[str, ...]] = ("sample_hash", "rate")


class SamplePlaybackRateRepository(Protocol):
    """Persistence for the effective rate each sample's note events settle on."""

    def replace_all(self, rate_by_hash: Mapping[str, Rate]) -> None: ...

    def get_many(self, sample_hashes: list[str]) -> dict[str, Rate]: ...

    def list_all(self) -> dict[str, Rate]: ...

    def count(self) -> int: ...

    def revision(self) -> tuple[int, int]: ...


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
        for chunk in chunks(sample_hashes, HASH_CHUNK_SIZE):
            statement = select(sample_playback_rate).where(sample_playback_rate.c.sample_hash.in_(chunk))
            rate_by_hash.update({row.sample_hash: row.rate for row in self._connection.execute(statement)})

        return rate_by_hash

    def list_all(self) -> dict[str, Rate]:
        """Every recorded rate at once, which is what a whole-catalog view needs to sound a click."""
        return {row.sample_hash: row.rate for row in self._connection.execute(select(sample_playback_rate))}

    def count(self) -> int:
        """How many rates are on file, which moves only when a whole pass replaces them all."""
        # pylint: disable-next=not-callable
        counted = self._connection.execute(select(func.count()).select_from(sample_playback_rate)).scalar_one()
        return int(counted)

    def revision(self) -> tuple[int, int]:
        """What the rates on file amount to: how many, and a sum of one hash per sample and rate.

        A pass that replaces the rates with as many new ones moves the sum whenever any sample's
        rate changed, so a reader holding an answer built from them can tell in one query.
        """
        digest = func.hashtextextended(
            sample_playback_rate.c.sample_hash + ":" + cast(sample_playback_rate.c.rate, String), 0
        )
        # pylint: disable-next=not-callable
        row = self._connection.execute(select(func.count(), func.coalesce(func.sum(digest), 0))).one()
        return int(row[0]), int(row[1])

    def rate_digest(self) -> str:
        """One digest over every recorded rate by sample, so a pass hearing samples as played can tell whether one moved."""
        statement = select(sample_playback_rate.c.sample_hash, sample_playback_rate.c.rate).order_by(
            sample_playback_rate.c.sample_hash
        )
        return digest_of_rows((str(row.sample_hash), int(row.rate)) for row in self._connection.execute(statement))
