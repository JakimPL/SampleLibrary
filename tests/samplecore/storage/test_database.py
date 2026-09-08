from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url

from samplecore.storage.curation import CURATION_SCHEMA
from samplecore.storage.database import SCHEMA_LOCK_KEY, connect, connect_for_curation, create_schema

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
            # str() on a URL renders its password as "***"; the yielded URL has to carry the real one.
            yield admin_url.set(database=database_name).render_as_string(hide_password=False)
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


def test_hand_labels_get_a_schema_of_their_own(connection: Connection) -> None:
    assert "sample_annotation" in set(inspect(connection).get_table_names(schema=CURATION_SCHEMA))


def test_a_curation_connection_prepares_labels_and_leaves_building_a_catalog_alone(
    fresh_database_url: str,
) -> None:
    """The served application owns the labels it records; the offline pipelines own the catalog."""
    connection = connect_for_curation(fresh_database_url)
    try:
        catalog_tables = set(inspect(connection).get_table_names())
        curation_tables = set(inspect(connection).get_table_names(schema=CURATION_SCHEMA))
    finally:
        connection.close()

    assert catalog_tables == set()
    assert curation_tables == {"sample_annotation"}


def test_creating_the_schema_holds_a_claim_no_other_run_can_take(connection: Connection, _database_url: str) -> None:
    """Two runs opening one fresh catalog would otherwise both try to create the same table.

    The second connection stands for that other run, asking for the claim rather than waiting on
    it, so the test reports the state instead of blocking on it.
    """
    with connect(_database_url) as other_run:
        create_schema(connection)
        while_creating = other_run.execute(select(func.pg_try_advisory_xact_lock(SCHEMA_LOCK_KEY))).scalar_one()
        connection.commit()
        once_created = other_run.execute(select(func.pg_try_advisory_xact_lock(SCHEMA_LOCK_KEY))).scalar_one()

    assert not while_creating
    assert once_created
