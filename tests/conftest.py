from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Final

import pytest
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import make_url

from samplecore.storage.curation import curation_metadata
from samplecore.storage.database import connect, metadata

SERVER_URL_VARIABLE: Final[str] = "SAMPLELIBRARY_TEST_DATABASE_URL"
DEFAULT_SERVER_URL: Final[str] = "postgresql+psycopg://samplelibrary:samplelibrary@localhost:5432/samplelibrary_test"


@pytest.fixture(scope="session")
def _server_url() -> str:
    """A local Postgres server to run the suite against, overridable for a server reachable elsewhere.

    The database this URL names is only ever connected to in order to create and drop the
    per-worker databases below, so it needs to exist but stays empty. The role it authenticates as
    needs ``CREATEDB``.
    """
    return os.environ.get(SERVER_URL_VARIABLE, DEFAULT_SERVER_URL)


@pytest.fixture(scope="session")
def _database_url(_server_url: str, worker_id: str) -> Iterator[str]:
    """A database of this test worker's own, created empty for the session and dropped after it.

    Running under ``pytest -n auto`` puts every worker on the same server, where the ``connection``
    fixture's habit of emptying every table between tests would otherwise reach into whatever the
    other workers are doing at that moment. One database per worker keeps that cleanup local to the
    worker performing it. ``CREATE DATABASE``/``DROP DATABASE`` cannot run inside a transaction
    block, hence the ``AUTOCOMMIT`` isolation level.
    """
    server_url = make_url(_server_url)
    database_name = f"{server_url.database}_{worker_id}"
    admin_engine = create_engine(server_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as admin_connection:
        admin_connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))
        admin_connection.execute(text(f'CREATE DATABASE "{database_name}"'))
        try:
            # str() on a URL renders its password as "***"; the yielded URL has to carry the real one.
            yield server_url.set(database=database_name).render_as_string(hide_password=False)
        finally:
            admin_connection.execute(text(f'DROP DATABASE "{database_name}" WITH (FORCE)'))
    admin_engine.dispose()


@pytest.fixture
def connection(_database_url: str) -> Iterator[Connection]:
    """A catalog connection to this worker's database, with an empty schema on every test.

    Emptying every table at teardown, in the same reverse-dependency order ``reset_library`` uses,
    gives each test the same "starts from nothing" guarantee -- rolling back first discards any
    transaction a failing test left open, so the cleanup deletes themselves always run against a
    clean transaction state.

    The curation tables are named here deliberately, since they live on a metadata of their own that
    ``reset_library`` has no reach into. A test wants them cleared between cases; a real library
    wants them kept, and that difference is exactly what the separate metadata buys.
    """
    open_connection = connect(_database_url)
    try:
        yield open_connection
    finally:
        open_connection.rollback()
        for table in [*reversed(metadata.sorted_tables), *reversed(curation_metadata.sorted_tables)]:
            open_connection.execute(table.delete())
        open_connection.commit()
        open_connection.close()
