from __future__ import annotations

from typing import Protocol

from sqlalchemy import Connection, delete, select
from sqlalchemy.dialects.postgresql import insert as upsert

from samplecore.models.pass_completion import PassCompletion, PassKind
from samplecore.storage.database import pass_completion


class PassCompletionRepository(Protocol):
    """Persistence for the record each whole-library pass leaves when it finishes completely."""

    def record(self, completion: PassCompletion) -> None: ...

    def get(self, kind: PassKind) -> PassCompletion | None: ...

    def forget(self, kind: PassKind) -> None: ...


class PostgresPassCompletionRepository:
    """A PassCompletionRepository backed by the catalog's ``pass_completion`` table, one row per kind of pass."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def record(self, completion: PassCompletion) -> None:
        """Make ``completion`` the last complete pass of its kind, replacing the one recorded before."""
        statement = upsert(pass_completion).values(
            kind=completion.kind.value, digest=completion.digest, completed_at=completion.completed_at
        )
        statement = statement.on_conflict_do_update(
            index_elements=[pass_completion.c.kind],
            set_={"digest": statement.excluded.digest, "completed_at": statement.excluded.completed_at},
        )
        self._connection.execute(statement)

    def get(self, kind: PassKind) -> PassCompletion | None:
        """The last complete pass of this kind, or nothing when none has finished since the catalog was emptied."""
        row = self._connection.execute(select(pass_completion).where(pass_completion.c.kind == kind.value)).fetchone()
        if row is None:
            return None
        return PassCompletion(kind=PassKind(row.kind), digest=row.digest, completed_at=row.completed_at)

    def forget(self, kind: PassKind) -> None:
        """Drop the record of this kind, for a pass that starts changing what its last complete pass left."""
        self._connection.execute(delete(pass_completion).where(pass_completion.c.kind == kind.value))

    def finished_over(self, kind: PassKind, digest: str) -> bool:
        """Whether the last complete pass of this kind had exactly this digest in front of it."""
        recorded = self.get(kind)
        return recorded is not None and recorded.digest == digest
