from __future__ import annotations

from collections.abc import Iterable
from typing import Final, Protocol

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection, Row, select, update
from sqlalchemy.dialects.postgresql import insert

from samplecore.models.fingerprint import SampleFingerprint, StoredFingerprint
from samplecore.storage.database import sample_fingerprint

# The vectors are kept as the bytes of little-endian single-precision floats.
VECTOR_DTYPE: Final[np.dtype[np.float32]] = np.dtype("<f4")


class SampleFingerprintRepository(Protocol):
    """Persistence for the equivalence fingerprints of samples, and for which of them have been compared."""

    def at_version(self, version: int) -> dict[str, StoredFingerprint]: ...

    def upsert_many(self, fingerprints: Iterable[SampleFingerprint], *, version: int) -> None: ...

    def mark_compared(self, sample_hashes: Iterable[str], *, comparison_version: int) -> None: ...

    def forget_comparisons(self) -> None: ...


class PostgresSampleFingerprintRepository:
    """A SampleFingerprintRepository backed by the catalog's ``sample_fingerprint`` table.

    A fingerprint written again replaces the one before and clears its comparison, since a sample
    read anew is compared anew.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def at_version(self, version: int) -> dict[str, StoredFingerprint]:
        """Every fingerprint read under `version`, by sample hash."""
        rows = self._connection.execute(
            select(sample_fingerprint).where(sample_fingerprint.c.version == version)
        ).fetchall()
        return {row.sample_hash: _row_to_stored(row) for row in rows}

    def upsert_many(self, fingerprints: Iterable[SampleFingerprint], *, version: int) -> None:
        values = [
            {
                "sample_hash": fingerprint.sample_hash,
                "version": version,
                "silent": fingerprint.silent,
                "trimmed_frames": fingerprint.trimmed_frames,
                "shape": _vector_bytes(fingerprint.shape),
                "rate": _vector_bytes(fingerprint.rate),
                "compared_version": None,
            }
            for fingerprint in fingerprints
        ]
        if not values:
            return
        statement = insert(sample_fingerprint)
        statement = statement.on_conflict_do_update(
            index_elements=[sample_fingerprint.c.sample_hash],
            set_={
                "version": statement.excluded.version,
                "silent": statement.excluded.silent,
                "trimmed_frames": statement.excluded.trimmed_frames,
                "shape": statement.excluded.shape,
                "rate": statement.excluded.rate,
                "compared_version": statement.excluded.compared_version,
            },
        )
        self._connection.execute(statement, values)

    def mark_compared(self, sample_hashes: Iterable[str], *, comparison_version: int) -> None:
        hashes = list(sample_hashes)
        if not hashes:
            return
        self._connection.execute(
            update(sample_fingerprint)
            .where(sample_fingerprint.c.sample_hash.in_(hashes))
            .values(compared_version=comparison_version)
        )

    def forget_comparisons(self) -> None:
        """Mark every sample as compared under no rule, so the next pass compares them all again."""
        self._connection.execute(update(sample_fingerprint).values(compared_version=None))


def _vector_bytes(vector: NDArray[np.float32] | None) -> bytes | None:
    return None if vector is None else np.asarray(vector, dtype=VECTOR_DTYPE).tobytes()


def _vector(content: bytes | None) -> NDArray[np.float32] | None:
    return None if content is None else np.frombuffer(content, dtype=VECTOR_DTYPE).astype(np.float32)


def _row_to_stored(row: Row[tuple[str, int, bool, int, bytes | None, bytes | None, int | None]]) -> StoredFingerprint:
    return StoredFingerprint(
        fingerprint=SampleFingerprint(
            sample_hash=row.sample_hash,
            trimmed_frames=row.trimmed_frames,
            shape=_vector(row.shape),
            rate=_vector(row.rate),
        ),
        compared_version=row.compared_version,
    )
