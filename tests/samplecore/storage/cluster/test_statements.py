from __future__ import annotations

import uuid
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import make_url

from samplecore.storage.cluster.quoting import UnsafeValueError, literal
from samplecore.storage.cluster.statements import (
    RoleAttributes,
    create_database,
    create_role,
    database_owner,
    role_attributes,
)


@pytest.fixture
def cluster_connection(_database_url: str) -> Iterator[Connection]:
    """A connection to the test server where CREATE DATABASE and CREATE ROLE are legal."""
    engine = create_engine(make_url(_database_url), isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        yield connection
    engine.dispose()


@pytest.fixture
def absent_database_name(cluster_connection: Connection) -> Iterator[str]:
    """A database name the server does not hold, dropped again whether or not a test creates it."""
    name = f"cluster_{uuid.uuid4().hex}"
    try:
        yield name
    finally:
        cluster_connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def test_the_test_server_reports_the_role_it_authenticates_as(cluster_connection: Connection, _server_url: str) -> None:
    attributes = role_attributes(cluster_connection, role=make_url(_server_url).username)

    assert attributes is not None
    assert attributes.may_create_databases


def test_a_role_the_server_does_not_know_reports_nothing(cluster_connection: Connection) -> None:
    assert role_attributes(cluster_connection, role=f"absent_{uuid.uuid4().hex}") is None


@pytest.mark.parametrize(
    ("attributes", "expected"),
    [
        (RoleAttributes(superuser=False, creates_databases=False), False),
        (RoleAttributes(superuser=False, creates_databases=True), True),
        (RoleAttributes(superuser=True, creates_databases=False), True),
    ],
)
def test_either_attribute_lets_a_role_create_databases(attributes: RoleAttributes, expected: bool) -> None:
    """A superuser made by hand carries `rolcreatedb` false and creates databases all the same."""
    assert attributes.may_create_databases is expected


def test_an_absent_database_has_no_owner(cluster_connection: Connection, absent_database_name: str) -> None:
    assert database_owner(cluster_connection, name=absent_database_name) is None


def test_a_created_database_belongs_to_the_role_it_was_created_for(
    cluster_connection: Connection, absent_database_name: str, _server_url: str
) -> None:
    owner = make_url(_server_url).username

    create_database(cluster_connection, name=absent_database_name, owner=owner)

    assert database_owner(cluster_connection, name=absent_database_name) == owner


def test_a_database_named_the_same_twice_is_refused_by_the_server(
    cluster_connection: Connection, absent_database_name: str, _server_url: str
) -> None:
    """What `provision` reads as "another run created it first"."""
    owner = make_url(_server_url).username
    create_database(cluster_connection, name=absent_database_name, owner=owner)

    with pytest.raises(psycopg.errors.DuplicateDatabase):
        create_database(cluster_connection, name=absent_database_name, owner=owner)


@pytest.mark.parametrize(
    "value",
    ["samplelibrary", "pa'ss", "back\\slash", 'quote"mark', "'; DROP DATABASE postgres; --", "  spaced  "],
)
def test_a_composed_value_reaches_the_server_as_the_value_it_stands_for(_server_url: str, value: str) -> None:
    """The path a password rides to ``CREATE ROLE`` on, proved against the server that receives it.

    Composition is the only thing standing between a password holding quote marks or backslashes
    and a statement meaning something else, so what matters is that the server hands the value back
    unchanged. A ``SELECT`` shows that on any connection, where creating a role to log in as needs
    a privilege this project's own role is deliberately without.
    """
    server_url = make_url(_server_url)
    with psycopg.connect(
        host=server_url.host,
        port=server_url.port,
        user=server_url.username,
        password=server_url.password,
        dbname=server_url.database,
    ) as opened:
        returned = opened.execute(sql.SQL("SELECT {}").format(literal(value))).fetchone()

    assert returned == (value,)


def test_a_created_role_may_log_in_with_the_password_it_was_given(
    cluster_connection: Connection, _server_url: str
) -> None:
    """The same guarantee end to end, where the connecting role may create one to try it with."""
    server_url = make_url(_server_url)
    role = f"cluster_{uuid.uuid4().hex}"[:32]
    password = "pa'ss\\word\"; DROP DATABASE postgres; --"

    try:
        create_role(cluster_connection, role=role, password=password)
    except psycopg.errors.InsufficientPrivilege:
        pytest.skip("the connecting role may not create roles")

    try:
        with psycopg.connect(
            host=server_url.host, port=server_url.port, user=role, password=password, dbname=server_url.database
        ) as opened:
            assert opened.execute("SELECT current_user").fetchone() == (role,)
    finally:
        cluster_connection.execute(text(f'DROP ROLE "{role}"'))


def test_a_name_quoting_cannot_carry_never_reaches_the_server(cluster_connection: Connection) -> None:
    with pytest.raises(UnsafeValueError):
        create_database(cluster_connection, name="na\x00me", owner="samplelibrary")
