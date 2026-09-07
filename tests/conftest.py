from __future__ import annotations

from collections.abc import Iterator
from typing import Final

import pytest
from sqlalchemy import Connection
from testcontainers.community.postgres import PostgresContainer

from samplecore.storage.database import connect, metadata

_POSTGRES_IMAGE: Final[str] = "postgres:17-alpine"


@pytest.fixture(scope="session")
def _database_url() -> Iterator[str]:
    """One Postgres container's connection URL, shared across the whole test session.

    Starting one container per test would dominate the suite's runtime with container startup
    rather than the tests themselves; per-test isolation instead comes from the ``connection``
    fixture emptying every table at teardown, not from a fresh container each time.
    """
    with PostgresContainer(_POSTGRES_IMAGE, driver="psycopg") as container:
        yield container.get_connection_url()


@pytest.fixture
def connection(_database_url: str) -> Iterator[Connection]:
    """A catalog connection to the shared test container, with an empty schema on every test.

    Emptying every table at teardown, in the same reverse-dependency order ``reset_library`` uses,
    gives each test the same "starts from nothing" guarantee an in-memory DuckDB connection used to
    give for free -- rolling back first discards any transaction a failing test left open, so the
    cleanup deletes themselves always run against a clean transaction state.
    """
    open_connection = connect(_database_url)
    try:
        yield open_connection
    finally:
        open_connection.rollback()
        for table in reversed(metadata.sorted_tables):
            open_connection.execute(table.delete())
        open_connection.commit()
        open_connection.close()
