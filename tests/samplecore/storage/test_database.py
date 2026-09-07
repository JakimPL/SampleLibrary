from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, create_engine, inspect, text
from sqlalchemy.engine import make_url

from samplecore.storage.database import connect, create_schema

EXPECTED_TABLES = frozenset(
    {"sample", "module", "sample_properties", "xm_sample_properties", "it_sample_properties", "sample_relation"}
)


@pytest.fixture
def fresh_database_url(_database_url: str) -> Iterator[str]:
    """A brand-new, empty database on the shared test server, with no schema created yet.

    The shared ``connection`` fixture's database always already has its schema in place (only its
    rows are emptied between tests), so it cannot exercise ``connect()``'s own first-use schema
    creation -- this creates and drops a genuinely fresh database on the same server for exactly
    that. ``CREATE DATABASE``/``DROP DATABASE`` cannot run inside a transaction block, hence the
    ``AUTOCOMMIT`` isolation level.
    """
    admin_url = make_url(_database_url)
    database_name = f"fresh_{uuid.uuid4().hex}"
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as admin_connection:
        admin_connection.execute(text(f'CREATE DATABASE "{database_name}"'))
        try:
            yield str(admin_url.set(database=database_name))
        finally:
            admin_connection.execute(text(f'DROP DATABASE "{database_name}" WITH (FORCE)'))
    admin_engine.dispose()


def test_create_schema_creates_every_expected_table(connection: Connection) -> None:
    tables = set(inspect(connection).get_table_names())

    assert EXPECTED_TABLES <= tables


def test_create_schema_is_idempotent(connection: Connection) -> None:
    create_schema(connection)
    create_schema(connection)


def test_connect_creates_the_schema_in_a_fresh_database(fresh_database_url: str) -> None:
    connection = connect(fresh_database_url)
    try:
        tables = set(inspect(connection).get_table_names())
    finally:
        connection.close()

    assert EXPECTED_TABLES <= tables


def test_a_read_only_connection_never_creates_the_schema(fresh_database_url: str) -> None:
    connection = connect(fresh_database_url, read_only=True)
    try:
        tables = set(inspect(connection).get_table_names())
    finally:
        connection.close()

    assert tables == set()
