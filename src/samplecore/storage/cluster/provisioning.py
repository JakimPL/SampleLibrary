from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from typing import Final

from psycopg import errors as postgres_errors
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.pool import NullPool

from samplecore.storage.cluster.quoting import UnsafeValueError, identifier
from samplecore.storage.cluster.statements import create_database, create_role, database_owner, role_attributes
from samplecore.storage.database import connect

# The disposable sandbox and the database the test suite bootstraps from keep names of their own,
# matching the Makefile's `DEV_DATABASE_URL` and the suite's own default server. Naming them here
# rather than deriving them from the configured library keeps all three in agreement whatever a
# person calls their own library, and keeps a URL that already names the sandbox from growing a
# second suffix when `make database` runs inside one of the `*-dev` targets' environment.
DEVELOPMENT_DATABASE: Final[str] = "samplelibrary_dev"
TEST_DATABASE: Final[str] = "samplelibrary_test"

ADMIN_URL_ENVIRONMENT_VARIABLE: Final[str] = "SAMPLELIBRARY_ADMIN_DATABASE_URL"

# Server-level work connects to a database other than the ones it creates. `postgres` is present on
# every ordinary cluster, `template1` on every cluster there is.
MAINTENANCE_DATABASES: Final[tuple[str, ...]] = ("postgres", "template1")

_SERVER_UNREACHABLE_FRAGMENTS: Final[tuple[str, ...]] = (
    "Connection refused",
    "could not translate host name",
    "timeout expired",
    "No such file or directory",
)
_PASSWORD_REJECTED_FRAGMENT: Final[str] = "password authentication failed"
_ROLE_MISSING_FRAGMENTS: Final[tuple[str, str]] = ('role "', "does not exist")
_DATABASE_MISSING_FRAGMENTS: Final[tuple[str, str]] = ('database "', "does not exist")
_UNNAMED_ROLE: Final[str] = "(none)"


class ProvisioningError(Exception):
    """Raised when the server cannot be prepared, carrying the steps that would let it be.

    ``remedy`` holds the lines a person should act on, each ready to print on a line of its own.
    """

    def __init__(self, message: str, *, remedy: tuple[str, ...]) -> None:
        super().__init__(message)
        self.remedy = remedy


@dataclass(frozen=True)
class DatabaseOutcome:
    """One database this pass looked for, the role owning it, and whether it had to create it."""

    name: str
    owner: str
    created: bool


@dataclass(frozen=True)
class ProvisioningSummary:
    """What one provisioning pass found on the server, and what it added."""

    server: str
    role: str
    role_created: bool
    role_creates_databases: bool
    databases: tuple[DatabaseOutcome, ...]
    schemas_prepared: tuple[str, ...]


def library_databases(database_url: str) -> tuple[str, ...]:
    """The three databases this project keeps on one server, the configured library leading.

    Raises:
        ProvisioningError: the URL names no database.
    """
    library = make_url(database_url).database
    if library is None:
        raise ProvisioningError(
            f"Your database_url names no database: {make_url(database_url).render_as_string()}",
            remedy=("Name one, as in postgresql+psycopg://samplelibrary:samplelibrary@localhost:5432/samplelibrary",),
        )

    return (library, DEVELOPMENT_DATABASE, TEST_DATABASE)


def login_role(database_url: str) -> str:
    """The role a URL logs in as.

    Raises:
        ProvisioningError: the URL names no role.
    """
    role = make_url(database_url).username
    if role is None:
        raise ProvisioningError(
            f"Your database_url names no role to log in as: {make_url(database_url).render_as_string()}",
            remedy=("Name one, as in postgresql+psycopg://samplelibrary:samplelibrary@localhost:5432/samplelibrary",),
        )

    return role


def admin_urls(database_url: str) -> tuple[URL, ...]:
    """The connections to try for server-level work, the most explicitly chosen one leading.

    ``SAMPLELIBRARY_ADMIN_DATABASE_URL`` names a connection carrying the privilege to create a role,
    which a library's own credentials rarely have. Left unset, the library's own URL is reused
    against a maintenance database, which is all a role that already exists needs in order to create
    the databases it will own.
    """
    explicit_url = os.environ.get(ADMIN_URL_ENVIRONMENT_VARIABLE)
    if explicit_url is not None:
        return (make_url(explicit_url),)

    library_url = make_url(database_url)
    return tuple(library_url.set(database=name) for name in MAINTENANCE_DATABASES)


def describe_server(url: URL) -> str:
    """A server named the way a person recognizes it, carrying no password."""
    return f"{url.host}:{url.port}"


@contextmanager
def open_admin_connection(database_url: str) -> Iterator[Connection]:
    """Open a connection for server-level work, closing it and its engine again afterward.

    ``AUTOCOMMIT`` is what makes ``CREATE DATABASE`` and ``CREATE ROLE`` available at all, both
    being statements Postgres runs outside a transaction block.

    Raises:
        ProvisioningError: every candidate connection was refused.
    """
    engine, connection = _open_admin(database_url)
    try:
        yield connection
    finally:
        connection.close()
        engine.dispose()


def provision(database_url: str) -> ProvisioningSummary:
    """Create the role and the three databases this project expects, where they are missing.

    Every step looks at ``pg_catalog`` first and adds only what is absent, so a library already in
    use comes through untouched: the catalog keeps its rows, and so does the ``curation`` schema
    holding a person's own labels, ratings, and favorites. The library and the development sandbox
    then have their tables brought into existence, which leaves each ready to serve or extract into.
    The test database stays empty, being the one the suite connects to only in order to create and
    drop a database per worker.

    Raises:
        ProvisioningError: the configuration names something Postgres cannot be asked for, or the
            server refused every connection, or refused a statement this needs.
    """
    library_url = make_url(database_url)
    role = login_role(database_url)
    library_name, development_name, _ = library_databases(database_url)
    _require_nameable(role, library_name, development_name, TEST_DATABASE)

    with open_admin_connection(database_url) as connection:
        role_created = _claim_role(connection, url=library_url, role=role)
        outcomes = tuple(
            _claim_database(connection, name=name, owner=role)
            for name in (library_name, DEVELOPMENT_DATABASE, TEST_DATABASE)
        )
        attributes = role_attributes(connection, role=role)

    prepared = (library_name, development_name)
    for outcome in outcomes:
        if outcome.name in prepared:
            _require_ownership(outcome, role=role)
    for name in prepared:
        _prepare_schemas(library_url.set(database=name), role=role)

    return ProvisioningSummary(
        server=describe_server(library_url),
        role=role,
        role_created=role_created,
        role_creates_databases=attributes is not None and attributes.may_create_databases,
        databases=outcomes,
        schemas_prepared=prepared,
    )


def _require_nameable(*values: str) -> None:
    """Insist that every name this pass will ask Postgres for survives being quoted as itself.

    Raises:
        ProvisioningError: a name would reach the server as something else.
    """
    for value in values:
        try:
            identifier(value)
        except UnsafeValueError as error:
            raise ProvisioningError(
                str(error), remedy=("Correct the role and database your database_url names.",)
            ) from error


def connection_remedy(url: URL, message: str) -> tuple[str, ...]:
    """What to do about a refused connection, read from the words Postgres refused it with.

    Postgres answers a missing role and a wrong password alike on purpose, so where it does, both
    are named and a person picks the one that applies.
    """
    role = url.username if url.username is not None else _UNNAMED_ROLE
    password = url.password if url.password is not None else ""

    if any(fragment in message for fragment in _SERVER_UNREACHABLE_FRAGMENTS):
        return (
            f"Start Postgres, or correct the host and port your database_url names ({describe_server(url)}).",
            "A container is one way to have one: docker compose up -d postgres",
        )

    if _PASSWORD_REJECTED_FRAGMENT in message:
        return (
            f"Role {role!r} either does not exist yet, or its password differs from your database_url's.",
            *role_creation_remedy(role, password),
            "Or, where it exists under another password:",
            f"    sudo -u postgres psql -c \"ALTER ROLE {role} PASSWORD '{password}'\"",
        )

    if all(fragment in message for fragment in _ROLE_MISSING_FRAGMENTS):
        return role_creation_remedy(role, password)

    if all(fragment in message for fragment in _DATABASE_MISSING_FRAGMENTS):
        return (
            f"This server keeps none of the databases server-level work connects through "
            f"({', '.join(MAINTENANCE_DATABASES)}).",
            f"Point {ADMIN_URL_ENVIRONMENT_VARIABLE} at a database on it that role {role!r} may reach.",
        )

    return (f"Check that {describe_server(url)} is the server you meant, and that role {role!r} may reach it.",)


def role_creation_remedy(role: str, password: str) -> tuple[str, ...]:
    """The one command that creates this project's login role, and the way to avoid needing it."""
    return (
        "Creating a role needs a Postgres superuser. Run this once, then run `make database` again:",
        f"    sudo -u postgres psql -c \"CREATE ROLE {role} WITH LOGIN CREATEDB PASSWORD '{password}'\"",
        f"Or point {ADMIN_URL_ENVIRONMENT_VARIABLE} at a superuser connection, and this creates it for you.",
    )


def _open_admin(database_url: str) -> tuple[Engine, Connection]:
    """Open the first admin connection a candidate URL grants.

    Raises:
        ProvisioningError: every candidate connection was refused.
    """
    candidates = admin_urls(database_url)
    refusal = ""
    for url in candidates:
        engine = create_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
        try:
            return engine, engine.connect()
        except OperationalError as error:
            refusal = server_message(error)
            engine.dispose()

    refused_url = candidates[-1]
    role = refused_url.username if refused_url.username is not None else _UNNAMED_ROLE
    raise ProvisioningError(
        f"Could not reach Postgres at {describe_server(refused_url)} as role {role!r}. "
        f"Postgres said: {headline(refusal)}",
        remedy=connection_remedy(refused_url, refusal),
    )


def server_message(error: DBAPIError) -> str:
    """Everything the driver itself contributed to a wrapped error.

    A refused connection arrives as several lines, the first stating what happened and the rest
    suggesting what to look at, so the whole of it is what a remedy reads.
    """
    return str(error.orig).strip() if error.orig is not None else str(error)


def headline(message: str) -> str:
    """The one line of a driver message that states what happened."""
    return message.splitlines()[0].strip()


def _claim_role(connection: Connection, *, url: URL, role: str) -> bool:
    """Create the login role where the server lacks it, reporting whether it was created.

    Raises:
        ProvisioningError: the role is absent, and either this connection may not create one or the
            configuration carries no password for it to log in with.
    """
    if role_attributes(connection, role=role) is not None:
        return False

    password = url.password
    if password is None:
        raise ProvisioningError(
            f"Role {role!r} is missing, and creating it needs the password it will log in with.",
            remedy=(f"Put one in your database_url, beside the {role!r} it already names.",),
        )

    try:
        create_role(connection, role=role, password=password)
    except postgres_errors.DuplicateObject:
        return False
    except postgres_errors.InsufficientPrivilege as error:
        raise ProvisioningError(
            f"Role {role!r} is missing, and this connection may not create one.",
            remedy=role_creation_remedy(role, password),
        ) from error

    return True


def _claim_database(connection: Connection, *, name: str, owner: str) -> DatabaseOutcome:
    """Create one database owned by ``owner`` where the server lacks it.

    Naming the owner is what lets that role create tables in the new database's ``public`` schema,
    which Postgres 15 onward grants to the database's owner rather than to everyone.

    Raises:
        ProvisioningError: the database is absent and this connection may not create one.
    """
    present_owner = database_owner(connection, name=name)
    if present_owner is not None:
        return DatabaseOutcome(name=name, owner=present_owner, created=False)

    try:
        create_database(connection, name=name, owner=owner)
    except postgres_errors.DuplicateDatabase:
        return DatabaseOutcome(name=name, owner=owner, created=False)
    except postgres_errors.InsufficientPrivilege as error:
        raise ProvisioningError(
            f"Database {name!r} is missing, and role {owner!r} may not create one.",
            remedy=(
                f'Grant it that: sudo -u postgres psql -c "ALTER ROLE {owner} CREATEDB"',
                f"Or point {ADMIN_URL_ENVIRONMENT_VARIABLE} at a connection that may create databases.",
            ),
        ) from error

    return DatabaseOutcome(name=name, owner=owner, created=True)


def _require_ownership(outcome: DatabaseOutcome, *, role: str) -> None:
    """Insist that the role about to create tables in a database is the role that owns it.

    Postgres 15 onward grants the ``public`` schema to a database's owner rather than to everyone,
    so ownership is what decides whether the catalog's tables can be created at all.

    Raises:
        ProvisioningError: another role owns the database.
    """
    if outcome.owner == role:
        return

    raise ProvisioningError(
        f"Database {outcome.name!r} belongs to role {outcome.owner!r}, so role {role!r} cannot "
        "create the catalog's tables in it.",
        remedy=(
            f"Hand it over, from a connection that may: "
            f'sudo -u postgres psql -c "ALTER DATABASE {outcome.name} OWNER TO {role}"',
            f"Or point your database_url at a library role {outcome.owner!r} owns.",
        ),
    )


def _prepare_schemas(url: URL, *, role: str) -> None:
    """Bring one database's catalog and curation schemas into existence.

    Raises:
        ProvisioningError: the role may not create them where they are missing.
    """
    try:
        with closing(connect(url.render_as_string(hide_password=False))):
            pass
    except DBAPIError as error:
        match error.orig:
            case postgres_errors.InsufficientPrivilege():
                raise ProvisioningError(
                    f"Role {role!r} may not create this project's tables in database {url.database!r}.",
                    remedy=(
                        f"Grant it what it needs, from a connection that may: "
                        f'sudo -u postgres psql -c "ALTER DATABASE {url.database} OWNER TO {role}"',
                    ),
                ) from error
            case _:
                raise
