from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from psycopg import Connection as PsycopgConnection
from psycopg import sql
from sqlalchemy import Connection, text

from samplecore.storage.cluster.quoting import identifier, literal

# Every statement this project runs against the cluster itself, rather than inside one database,
# lives here. The two lookups are ordinary queries and carry their values as bound parameters. The
# two that create something are utility statements, which Postgres binds no parameter into, so
# their values travel inside the statement text -- composed through `quoting`, which is the one
# place a name or a password is turned into a fragment of SQL.


@dataclass(frozen=True)
class RoleAttributes:
    """What a role may do, as far as preparing this project's databases depends on it."""

    superuser: bool
    creates_databases: bool

    @property
    def may_create_databases(self) -> bool:
        """Whether the role may create a database, which either attribute is enough for.

        A superuser made by hand carries ``rolcreatedb`` false and creates databases all the same,
        so reading the one attribute alone would understate what the role can do.
        """
        return self.superuser or self.creates_databases


def role_attributes(connection: Connection, *, role: str) -> RoleAttributes | None:
    """What the server allows the role of this name, where it knows one."""
    found = connection.execute(
        text("SELECT rolsuper, rolcreatedb FROM pg_catalog.pg_roles WHERE rolname = :role"), {"role": role}
    ).first()
    if found is None:
        return None

    return RoleAttributes(superuser=bool(found.rolsuper), creates_databases=bool(found.rolcreatedb))


def database_owner(connection: Connection, *, name: str) -> str | None:
    """The role owning the database of this name, where the server holds one."""
    owner = connection.execute(
        text("SELECT pg_catalog.pg_get_userbyid(datdba) FROM pg_catalog.pg_database WHERE datname = :name"),
        {"name": name},
    ).scalar()
    return str(owner) if owner is not None else None


def create_role(connection: Connection, *, role: str, password: str) -> None:
    """Create a login role that may create databases of its own.

    Raises:
        UnsafeValueError: the name or the password stands for something else once composed.
        psycopg.Error: the server refused the statement, a duplicate name and an insufficient
            privilege among the reasons it may.
    """
    _execute(
        connection,
        sql.SQL("CREATE ROLE {role} WITH LOGIN CREATEDB PASSWORD {password}").format(
            role=identifier(role), password=literal(password)
        ),
    )


def create_database(connection: Connection, *, name: str, owner: str) -> None:
    """Create a database belonging to the named role.

    Naming the owner is what lets that role create tables in the new database's ``public`` schema,
    which Postgres 15 onward grants to the database's owner rather than to everyone.

    Raises:
        UnsafeValueError: the name or the owner stands for something else once composed.
        psycopg.Error: the server refused the statement, a duplicate name and an insufficient
            privilege among the reasons it may.
    """
    _execute(
        connection,
        sql.SQL("CREATE DATABASE {name} OWNER {owner}").format(name=identifier(name), owner=identifier(owner)),
    )


def _execute(connection: Connection, statement: sql.Composed) -> None:
    """Send one composed statement over the ``psycopg`` connection underneath.

    Composition is the driver's own, so the statement is handed to the driver that composed it
    rather than rendered to a string for SQLAlchemy to send. The transaction caveat ``bulk_insert``
    documents stays clear of this path: these statements run on an ``AUTOCOMMIT`` connection, which
    leaves psycopg no transaction of its own to open.
    """
    driver_connection = cast(PsycopgConnection, connection.connection.dbapi_connection)
    driver_connection.execute(statement)
