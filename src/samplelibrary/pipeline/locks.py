from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from sqlalchemy import Connection, func, select, text
from sqlalchemy.exc import InterfaceError, OperationalError

from samplecore.storage.database import claim_named_lock, named_lock_key

PIPELINE_LOCK_PREFIX: Final[str] = "samplelibrary-pipeline"
_HELD_BY_THIS_BACKEND: Final[str] = """
SELECT EXISTS (
    SELECT 1 FROM pg_locks
    WHERE locktype = 'advisory' AND pid = pg_backend_pid()
      AND classid = :classid AND objid = :objid AND objsubid = 1
)
"""


def pipeline_lock_name(library_identity: str) -> str:
    """The lock one library's pipeline runs under, which tells it from every other library's."""
    return f"{PIPELINE_LOCK_PREFIX}-{library_identity}"


@dataclass(frozen=True)
class PipelineLock:
    """The one lock a library's pipeline runs under, held on a connection of its own.

    Postgres releases it the moment that connection goes, however the process ends, so a run whose
    process dies leaves the library open to the next run rather than locked against it. A run reads
    the lock back before each step, since a server restarted underneath it would have let go.
    """

    connection: Connection
    name: str

    def held(self) -> bool:
        """Whether this run still holds its lock, and its connection still answers at all."""
        key = named_lock_key(self.name) & 0xFFFFFFFFFFFFFFFF
        try:
            return bool(
                self.connection.execute(
                    text(_HELD_BY_THIS_BACKEND), {"classid": key >> 32, "objid": key & 0xFFFFFFFF}
                ).scalar_one()
            )
        except (OperationalError, InterfaceError):
            return False


def claim_pipeline_lock(connection: Connection, library_identity: str) -> PipelineLock | None:
    """Take a library's pipeline lock for as long as the connection stays open, or answer nothing when another run holds it."""
    name = pipeline_lock_name(library_identity)
    if not claim_named_lock(connection, name):
        return None
    return PipelineLock(connection=connection, name=name)


def step_is_running(connection: Connection, name: str) -> bool:
    """Whether a step of this name holds its own lock, which is what a process still running leaves.

    The lock is released again where it was free, so asking costs nothing and leaves nothing behind.
    """
    if not claim_named_lock(connection, name):
        return True
    connection.execute(select(func.pg_advisory_unlock(named_lock_key(name))))
    return False
