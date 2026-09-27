from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Final

from sqlalchemy import (
    ARRAY,
    Column,
    Connection,
    DateTime,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    delete,
    insert,
    text,
)
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateSchema

from samplecore.config import PUBLISH_DATABASE_URL_ENVIRONMENT_VARIABLE, PUBLISH_READER_PASSWORD_ENVIRONMENT_VARIABLE
from samplecore.passwords import MINIMUM_SERVICE_PASSWORD_LENGTH
from samplecore.storage.cluster.statements import create_service_role, role_attributes, set_role_password
from samplecore.storage.database import CONNECT_TIMEOUT_SECONDS
from sampleripper.publish.messages import (
    NO_READER_PASSWORD,
    NO_TARGET,
    NOT_A_PUBLICATION,
    SERVER_IN_SETTINGS,
    UNKNOWN_DRIVER,
    WEAK_READER_PASSWORD,
    WEAK_TRANSPORT,
)
from sampleserver.addresses import names_loopback

READER_ROLE: Final[str] = "samplelibrary_reader"
DRIVER_NAME: Final[str] = "postgresql+psycopg"
PLAIN_DRIVER_NAMES: Final[frozenset[str]] = frozenset({"postgresql", "postgres"})
SSL_MODE: Final[str] = "sslmode"
REQUIRED_SSL_MODE: Final[str] = "require"
SECURE_SSL_MODES: Final[frozenset[str]] = frozenset({"require", "verify-ca", "verify-full"})
CHANNEL_BINDING: Final[str] = "channel_binding"
REQUIRED_CHANNEL_BINDING: Final[str] = "require"
SERVER_SETTINGS: Final[tuple[str, ...]] = ("host", "hostaddr", "service")
PUBLICATION_SCHEMA: Final[str] = "publication"
# How long a publication waits for a site's reads to let the tables go before it gives up.
LOCK_TIMEOUT: Final[str] = "60s"

publication_metadata = MetaData(schema=PUBLICATION_SCHEMA)
publication_record = Table(
    "record",
    publication_metadata,
    Column("published_at", DateTime(timezone=True), primary_key=True),
    Column("sample_count", Integer, nullable=False),
    Column("directories", ARRAY(String), nullable=False),
)


class PublishRefusedError(Exception):
    """Raised when a publication may not go ahead; ``problems`` names each reason, one sentence apiece."""

    def __init__(self, problems: tuple[str, ...]) -> None:
        super().__init__(" ".join(problems))
        self.problems = problems


def target_url(environment: Mapping[str, str]) -> URL:
    """The database a publication is written to, as ``SAMPLERIPPER_PUBLISH_DATABASE_URL`` names it.

    A plain ``postgresql://`` URL, the form a hosting platform hands out, is read through psycopg.
    A server other than this computer is reached over TLS whose handshake the password itself binds
    (``channel_binding=require``), so a server presenting a certificate no authority signed, as a
    platform's proxy does, cannot stand between the two unnoticed.

    The server is named where the URL's host goes, and nowhere else, so the TLS requirement follows
    the server the connection reaches.

    Raises:
        PublishRefusedError: the variable is missing, names another database, names its server in a
            setting, or asks for TLS weaker than required.
    """
    raw = environment.get(PUBLISH_DATABASE_URL_ENVIRONMENT_VARIABLE)
    if not raw:
        raise PublishRefusedError((NO_TARGET,))
    try:
        url = make_url(raw)
    except ArgumentError as error:
        raise PublishRefusedError((NO_TARGET,)) from error
    if url.drivername in PLAIN_DRIVER_NAMES:
        url = url.set(drivername=DRIVER_NAME)
    if url.drivername != DRIVER_NAME:
        raise PublishRefusedError((UNKNOWN_DRIVER.format(name=url.drivername),))
    for setting in SERVER_SETTINGS:
        if setting in url.query:
            raise PublishRefusedError((SERVER_IN_SETTINGS.format(name=setting),))
    if url.host is None or names_loopback(url.host):
        return url
    mode = url.query.get(SSL_MODE)
    if mode is not None and mode not in SECURE_SSL_MODES:
        raise PublishRefusedError((WEAK_TRANSPORT.format(host=url.host, mode=mode),))
    return url.update_query_dict({SSL_MODE: str(mode or REQUIRED_SSL_MODE), CHANNEL_BINDING: REQUIRED_CHANNEL_BINDING})


def reader_password(environment: Mapping[str, str]) -> str:
    """The password the site's reader logs in with, as ``SAMPLERIPPER_PUBLISH_READER_PASSWORD`` names it.

    Raises:
        PublishRefusedError: the variable is missing, or names a password short enough to have been chosen.
    """
    password = environment.get(PUBLISH_READER_PASSWORD_ENVIRONMENT_VARIABLE)
    if not password:
        raise PublishRefusedError((NO_READER_PASSWORD,))
    if len(password) < MINIMUM_SERVICE_PASSWORD_LENGTH:
        raise PublishRefusedError((WEAK_READER_PASSWORD.format(length=MINIMUM_SERVICE_PASSWORD_LENGTH),))
    return password


def target_engine(url: URL) -> Engine:
    """An engine for the one connection a publication writes through, opening no pool."""
    return create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS})


def refuse_a_foreign_catalog(connection: Connection) -> None:
    """Insist that the database holds no catalog, or the one a publication wrote, before anything in it changes.

    A publication replaces every row of the catalog it writes to; a database holding a catalog with
    no record of a publication is someone's library, the one publishing among them, and is left alone.

    Raises:
        PublishRefusedError: the database holds a catalog no publication wrote.
    """
    holds_catalog, published = connection.execute(
        text("SELECT to_regclass('public.sample') IS NOT NULL, to_regclass(:record) IS NOT NULL"),
        {"record": publication_record.fullname},
    ).one()
    connection.rollback()
    if holds_catalog and not published:
        raise PublishRefusedError((NOT_A_PUBLICATION,))


def claim_tables(connection: Connection) -> None:
    """Wait at most `LOCK_TIMEOUT` for the tables a publication replaces, which a running site may be reading."""
    connection.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))


def prepare_reader(connection: Connection, *, password: str) -> None:
    """Have the site's reader log in with ``password``, creating it with no power over the server where it is missing.

    Everything in the database is readable by the database's owner and no one else once the reader
    is granted what it needs, which the caller does next; creating in the ``public`` schema is taken
    from everyone as well, which a server older than Postgres 15 still grants.
    """
    if role_attributes(connection, role=READER_ROLE) is None:
        create_service_role(connection, role=READER_ROLE, password=password)
    else:
        set_role_password(connection, role=READER_ROLE, password=password)
    connection.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))


def record_publication(
    connection: Connection, *, published_at: datetime, sample_count: int, names: tuple[str, ...]
) -> None:
    """Record the publication, in a schema of its own, as the mark that the catalog here is a publication's."""
    connection.execute(CreateSchema(PUBLICATION_SCHEMA, if_not_exists=True))
    connection.execute(text(f"REVOKE ALL ON SCHEMA {PUBLICATION_SCHEMA} FROM PUBLIC"))
    publication_metadata.create_all(connection)
    connection.execute(delete(publication_record))
    connection.execute(
        insert(publication_record).values(published_at=published_at, sample_count=sample_count, directories=list(names))
    )
