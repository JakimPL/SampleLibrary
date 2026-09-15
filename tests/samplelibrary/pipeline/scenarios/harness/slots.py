from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Final

from sqlalchemy import Connection, Engine, create_engine, func, select, text

from samplecore.storage.database import claim_named_lock, named_lock_key

SLOT_LOCK_PREFIX: Final[str] = "samplelibrary-tests-scenario-slot"
# A world's runs were measured at five connections beside its test's own; one more covers a lock a scenario holds.
SCENARIO_CONNECTIONS: Final[int] = 6
# A test's own connection, and the one a slot is waited for and held on.
CONNECTIONS_PER_TEST_WORKER: Final[int] = 2
WORKER_COUNT_VARIABLE: Final[str] = "PYTEST_XDIST_WORKER_COUNT"
SLOT_POLL_SECONDS: Final[float] = 0.2
SLOT_DEADLINE_SECONDS: Final[float] = 1800.0


@dataclass(frozen=True)
class ScenarioSlot:
    """One of the slots the server's connections leave room for, held while a scenario's worlds stand.

    A world's runs open connections of their own, from the orchestrator and from every step, so
    worlds acting all at once on every test worker would take more connections than the server
    accepts. Each slot is an advisory lock on the server's own database, which every test worker
    and every test session on that server shares.
    """

    engine: Engine
    connection: Connection
    name: str

    def release(self) -> None:
        self.connection.execute(select(func.pg_advisory_unlock(named_lock_key(self.name))))
        self.connection.close()
        self.engine.dispose()


def claim_scenario_slot(server_url: str) -> ScenarioSlot:
    """Wait for a slot to come free and hold it on a connection of its own.

    Raises:
        AssertionError: no slot came free within the deadline.
    """
    engine = create_engine(server_url)
    connection = engine.connect()
    slots = _slot_count(connection)
    deadline = time.monotonic() + SLOT_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        for index in range(slots):
            name = f"{SLOT_LOCK_PREFIX}-{index}"
            claimed = claim_named_lock(connection, name)
            connection.commit()
            if claimed:
                return ScenarioSlot(engine=engine, connection=connection, name=name)
        time.sleep(SLOT_POLL_SECONDS)
    connection.close()
    engine.dispose()
    raise AssertionError(f"no scenario slot of {slots} came free within {SLOT_DEADLINE_SECONDS:.0f} s")


def _slot_count(connection: Connection) -> int:
    """How many worlds the server carries at once beside the connections every test worker keeps open."""
    maximum, superuser_reserved, reserved = connection.execute(
        text(
            "SELECT current_setting('max_connections')::int,"
            " current_setting('superuser_reserved_connections')::int,"
            " coalesce(current_setting('reserved_connections', true), '0')::int"
        )
    ).one()
    connection.commit()
    workers = int(os.environ.get(WORKER_COUNT_VARIABLE, "1"))
    usable = maximum - superuser_reserved - reserved - workers * CONNECTIONS_PER_TEST_WORKER
    return max(1, usable // SCENARIO_CONNECTIONS)
