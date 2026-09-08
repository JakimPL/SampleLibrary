from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Connection, create_engine, inspect, text
from sqlalchemy.engine import make_url

from samplecore.models.annotation import AnnotationSource, SampleAnnotation
from samplecore.models.sample_properties import SampleOccurrence
from samplecore.storage.cluster.provisioning import (
    ADMIN_URL_ENVIRONMENT_VARIABLE,
    DEVELOPMENT_DATABASE,
    MAINTENANCE_DATABASES,
    TEST_DATABASE,
    DatabaseOutcome,
    ProvisioningError,
    admin_urls,
    connection_remedy,
    library_databases,
    login_role,
)
from samplecore.storage.curation import CURATION_SCHEMA
from samplecore.storage.database import connect
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository

_ROLELESS_URL = "postgresql+psycopg://localhost:5432/samplelibrary"
_DATABASELESS_URL = "postgresql+psycopg://samplelibrary:samplelibrary@localhost:5432"
_LIBRARY_URL = make_url("postgresql+psycopg://samplelibrary:samplelibrary@localhost:5432/samplelibrary")


@pytest.fixture
def cluster_connection(_database_url: str) -> Iterator[Connection]:
    """A connection to the test server where CREATE DATABASE is legal."""
    engine = create_engine(make_url(_database_url), isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        yield connection
    engine.dispose()


@pytest.fixture
def prepared_database_url(cluster_connection: Connection, _database_url: str) -> Iterator[str]:
    """A database of this test's own, created empty and dropped afterward."""
    server_url = make_url(_database_url)
    name = f"provision_{uuid.uuid4().hex}"
    cluster_connection.execute(text(f'CREATE DATABASE "{name}" OWNER "{server_url.username}"'))
    try:
        yield server_url.set(database=name).render_as_string(hide_password=False)
    finally:
        cluster_connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))


def test_library_databases_leads_with_the_configured_library() -> None:
    library, development, test_database = library_databases(
        "postgresql+psycopg://samplelibrary:samplelibrary@localhost:5432/my_own_library"
    )

    assert library == "my_own_library"
    assert (development, test_database) == (DEVELOPMENT_DATABASE, TEST_DATABASE)


def test_library_databases_keeps_the_companions_of_a_sandbox_url_unsuffixed() -> None:
    """A URL already naming the sandbox yields the same companions, rather than nesting suffixes."""
    _, development, test_database = library_databases(
        f"postgresql+psycopg://samplelibrary:samplelibrary@localhost:5432/{DEVELOPMENT_DATABASE}"
    )

    assert (development, test_database) == (DEVELOPMENT_DATABASE, TEST_DATABASE)


def test_library_databases_reports_a_url_naming_no_database() -> None:
    with pytest.raises(ProvisioningError):
        library_databases(_DATABASELESS_URL)


def test_login_role_reads_the_role_a_url_logs_in_as() -> None:
    assert login_role("postgresql+psycopg://someone:secret@localhost:5432/samplelibrary") == "someone"


def test_login_role_reports_a_url_naming_no_role() -> None:
    with pytest.raises(ProvisioningError):
        login_role(_ROLELESS_URL)


def test_admin_urls_reuse_the_library_credentials_against_maintenance_databases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ADMIN_URL_ENVIRONMENT_VARIABLE, raising=False)

    urls = admin_urls("postgresql+psycopg://samplelibrary:secret@example.test:5433/my_own_library")

    assert tuple(url.database for url in urls) == MAINTENANCE_DATABASES
    assert {(url.username, url.password, url.host, url.port) for url in urls} == {
        ("samplelibrary", "secret", "example.test", 5433)
    }


def test_admin_urls_prefer_the_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ADMIN_URL_ENVIRONMENT_VARIABLE, "postgresql+psycopg://root:root@example.test:5433/postgres")

    urls = admin_urls("postgresql+psycopg://samplelibrary:secret@localhost:5432/my_own_library")

    assert [url.username for url in urls] == ["root"]


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("connection failed: ... failed: Connection refused", "docker compose up -d postgres"),
        ('connection failed: FATAL:  password authentication failed for user "samplelibrary"', "CREATE ROLE"),
        ('connection failed: FATAL:  role "samplelibrary" does not exist', "CREATE ROLE"),
        ('connection failed: FATAL:  database "template1" does not exist', ADMIN_URL_ENVIRONMENT_VARIABLE),
        ("connection failed: something else entirely", "is the server you meant"),
    ],
)
def test_a_refusal_is_answered_with_what_addresses_it(message: str, expected: str) -> None:
    """Postgres answers a missing role and a wrong password alike, so that one names both."""
    assert expected in "\n".join(connection_remedy(_LIBRARY_URL, message))


def test_a_password_rejection_names_both_of_the_causes_it_could_have() -> None:
    remedy = "\n".join(
        connection_remedy(_LIBRARY_URL, 'FATAL:  password authentication failed for user "samplelibrary"')
    )

    assert "CREATE ROLE" in remedy
    assert "ALTER ROLE" in remedy


def test_preparing_a_fresh_database_creates_both_schemas(prepared_database_url: str) -> None:
    """What `provision` leaves behind in each database it prepares."""
    connection = connect(prepared_database_url)
    try:
        inspector = inspect(connection)
        assert "sample" in inspector.get_table_names()
        assert "sample_annotation" in inspector.get_table_names(schema=CURATION_SCHEMA)
    finally:
        connection.close()


def test_preparing_a_database_twice_keeps_the_annotations_it_holds(prepared_database_url: str) -> None:
    """The one thing nothing here can rebuild survives a database being prepared again."""
    annotation = SampleAnnotation(
        sample_hash="a" * 64,
        label="kick drum",
        rating=5,
        favorite=True,
        module_filename="song.xm",
        occurrence=SampleOccurrence(module_hash="b" * 64, instrument_index=1, sample_slot=0),
        sample_name="kick",
        source=AnnotationSource.SAMPLE,
        annotated_at=datetime.now(UTC),
    )

    connection = connect(prepared_database_url)
    try:
        PostgresSampleAnnotationRepository(connection).replace_many((annotation,))
        connection.commit()
    finally:
        connection.close()

    reopened = connect(prepared_database_url)
    try:
        kept = PostgresSampleAnnotationRepository(reopened).list_all()
    finally:
        reopened.close()

    assert kept == (annotation,)


def test_a_database_outcome_names_what_it_found() -> None:
    outcome = DatabaseOutcome(name="samplelibrary", owner="samplelibrary", created=False)

    assert (outcome.name, outcome.owner, outcome.created) == ("samplelibrary", "samplelibrary", False)
