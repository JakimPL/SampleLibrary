from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import Connection, Row, func, select
from sqlalchemy.dialects.postgresql import insert

from samplecore.models.sample_file import FileFingerprint, SampleFile, SampleFileLocation
from samplecore.storage.database import HASH_CHUNK_SIZE, chunks, sample_file


class SampleFileRepository(Protocol):
    """Persistence for the plain audio files the library reads in place."""

    def upsert(self, sample_file_row: SampleFile) -> None: ...

    def get(self, location: SampleFileLocation) -> SampleFile | None: ...

    def list_for_samples(self, sample_hashes: Sequence[str]) -> tuple[SampleFile, ...]: ...

    def list_all(self) -> tuple[SampleFile, ...]: ...

    def count(self) -> int: ...


class PostgresSampleFileRepository:
    """A SampleFileRepository backed by the catalog's ``sample_file`` table.

    ``upsert`` replaces what a location holds: a file rewritten in place decodes to another sample,
    and the location follows it to that sample's hash, rate and fingerprint. Listings come in
    directory and path order, which is the order a reader tries a sample's files in.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def upsert(self, sample_file_row: SampleFile) -> None:
        statement = insert(sample_file).values(
            directory=sample_file_row.location.directory.as_posix(),
            relative_path=sample_file_row.location.relative_path,
            sample_hash=sample_file_row.sample_hash,
            rate=sample_file_row.rate,
            size_bytes=sample_file_row.fingerprint.size_bytes,
            modified_ns=sample_file_row.fingerprint.modified_ns,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[sample_file.c.directory, sample_file.c.relative_path],
            set_={
                "sample_hash": statement.excluded.sample_hash,
                "rate": statement.excluded.rate,
                "size_bytes": statement.excluded.size_bytes,
                "modified_ns": statement.excluded.modified_ns,
            },
        )
        self._connection.execute(statement)

    def get(self, location: SampleFileLocation) -> SampleFile | None:
        row = self._connection.execute(
            select(sample_file).where(
                sample_file.c.directory == location.directory.as_posix(),
                sample_file.c.relative_path == location.relative_path,
            )
        ).fetchone()
        return _row_to_sample_file(row) if row is not None else None

    def list_for_samples(self, sample_hashes: Sequence[str]) -> tuple[SampleFile, ...]:
        rows: list[Row[Any]] = []
        for chunk in chunks(sample_hashes, HASH_CHUNK_SIZE):
            narrowed = select(sample_file).where(sample_file.c.sample_hash.in_(chunk))
            rows.extend(self._connection.execute(narrowed).fetchall())
        return _in_location_order(rows)

    def list_all(self) -> tuple[SampleFile, ...]:
        return _in_location_order(self._connection.execute(select(sample_file)).fetchall())

    def count(self) -> int:
        # pylint: disable-next=not-callable
        counted = self._connection.execute(select(func.count()).select_from(sample_file)).scalar_one()
        return int(counted)


def _in_location_order(rows: Sequence[Row[Any]]) -> tuple[SampleFile, ...]:
    """The rows as sample files, sorted in Python so the order stays the same whatever collation the database uses."""
    return tuple(sorted((_row_to_sample_file(row) for row in rows), key=lambda found: found.location.sort_key))


def _row_to_sample_file(row: Row[Any]) -> SampleFile:
    return SampleFile(
        sample_hash=row.sample_hash,
        location=SampleFileLocation(directory=Path(row.directory), relative_path=row.relative_path),
        rate=row.rate,
        fingerprint=FileFingerprint(size_bytes=row.size_bytes, modified_ns=row.modified_ns),
    )
