from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Connection, create_engine, inspect, text
from sqlalchemy.engine import URL, make_url

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE, DATABASE_URL_ENVIRONMENT_VARIABLE
from samplecore.models.annotation import AnnotationSource, ModuleSlotAnchor, SampleAnnotation
from samplecore.models.sample_properties import SampleOccurrence
from samplecore.models.service_role import ServiceRole
from samplecore.storage.cluster.embedded.state import managed_catalog_url
from samplecore.storage.cluster.provisioning import (
    ADMIN_URL_ENVIRONMENT_VARIABLE,
    DEVELOPMENT_DATABASE,
    MAINTENANCE_DATABASES,
    TEST_DATABASE,
    ConnectionSource,
    DatabaseOutcome,
    ProvisioningError,
    admin_urls,
    connection_remedy,
    connection_source,
    describe_server,
    describe_source,
    development_database_url,
    library_databases,
    login_role,
    password_value,
    provision,
    server_address,
    statement_value,
)
from samplecore.storage.curation import CURATION_SCHEMA
from samplecore.storage.database import connect
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository

_ROLELESS_URL = "postgresql+psycopg://localhost:5432/sampleripper"
_DATABASELESS_URL = "postgresql+psycopg://sampleripper:not-a-real-password@localhost:5432"
_LIBRARY_URL = make_url("postgresql+psycopg://sampleripper:not-a-real-password@localhost:5432/sampleripper")


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


def _remedy(
    message: str, *, url: URL = _LIBRARY_URL, source: ConnectionSource = ConnectionSource.CONFIGURATION
) -> tuple[str, ...]:
    """The advice one refusal earns, read the way the command reads it."""
    return connection_remedy(url, message, source=source)


def test_library_databases_leads_with_the_configured_library() -> None:
    library, development, test_database = library_databases(
        "postgresql+psycopg://sampleripper:not-a-real-password@localhost:5432/my_own_library"
    )

    assert library == "my_own_library"
    assert (development, test_database) == (DEVELOPMENT_DATABASE, TEST_DATABASE)


def test_library_databases_names_the_sandbox_once_for_a_sandbox_url() -> None:
    """A URL already naming the sandbox yields the same companions, each named once."""
    databases = library_databases(
        f"postgresql+psycopg://sampleripper:not-a-real-password@localhost:5432/{DEVELOPMENT_DATABASE}"
    )

    assert databases == (DEVELOPMENT_DATABASE, TEST_DATABASE)


def test_the_development_database_shares_the_library_server_role_and_password() -> None:
    url = make_url(development_database_url("postgresql+psycopg://someone:secret@elsewhere:5433/my_own_library"))

    assert (url.host, url.port, url.username, url.password) == ("elsewhere", 5433, "someone", "secret")
    assert url.database == DEVELOPMENT_DATABASE


def test_library_databases_reports_a_url_naming_no_database() -> None:
    with pytest.raises(ProvisioningError):
        library_databases(_DATABASELESS_URL)


def test_login_role_reads_the_role_a_url_logs_in_as() -> None:
    assert login_role("postgresql+psycopg://someone:secret@localhost:5432/sampleripper") == "someone"


def test_login_role_reports_a_url_naming_no_role() -> None:
    with pytest.raises(ProvisioningError):
        login_role(_ROLELESS_URL)


def test_admin_urls_reuse_the_library_credentials_against_maintenance_databases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ADMIN_URL_ENVIRONMENT_VARIABLE, raising=False)

    urls = admin_urls("postgresql+psycopg://sampleripper:secret@example.test:5433/my_own_library")

    assert tuple(url.database for url in urls) == MAINTENANCE_DATABASES
    assert {(url.username, url.password, url.host, url.port) for url in urls} == {
        ("sampleripper", "secret", "example.test", 5433)
    }


def test_admin_urls_prefer_the_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ADMIN_URL_ENVIRONMENT_VARIABLE, "postgresql+psycopg://root:root@example.test:5433/postgres")

    urls = admin_urls("postgresql+psycopg://sampleripper:secret@localhost:5432/my_own_library")

    assert [url.username for url in urls] == ["root"]


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("connection failed: ... failed: Connection refused", "docker compose up -d postgres"),
        ('connection failed: FATAL:  password authentication failed for user "sampleripper"', "CREATE ROLE"),
        ('connection failed: FATAL:  role "sampleripper" does not exist', "CREATE ROLE"),
        ('connection failed: FATAL:  database "template1" does not exist', ADMIN_URL_ENVIRONMENT_VARIABLE),
        ("connection failed: something else entirely", "is the server you meant"),
    ],
)
def test_a_refusal_is_answered_with_what_addresses_it(message: str, expected: str) -> None:
    """Postgres answers a missing role and a wrong password alike, so that one names both."""
    assert expected in "\n".join(_remedy(message))


def test_a_password_rejection_names_both_of_the_causes_it_could_have() -> None:
    """Postgres reports a missing role and a wrong password alike, so the wording covers both."""
    remedy = "\n".join(_remedy('FATAL:  password authentication failed for user "sampleripper"'))

    assert "does not exist on this" in remedy
    assert "password there is different" in remedy


def test_a_refusal_quotes_what_postgres_reported_without_the_driver_wrapping() -> None:
    remedy = "\n".join(
        _remedy(
            'connection failed: connection to server at "127.0.0.1", port 5432 failed: '
            'FATAL:  password authentication failed for user "sampleripper"',
        )
    )

    assert 'Postgres said: password authentication failed for user "sampleripper"' in remedy
    assert "connection failed:" not in remedy


@pytest.mark.parametrize("role", ["user", "group", "sampleripper", "Mixed Case"])
def test_the_statement_a_person_is_told_to_run_names_the_role_as_postgres_reads_it(role: str) -> None:
    """`CREATE ROLE user` is a syntax error, `user` being a word Postgres keeps for itself."""
    url = _LIBRARY_URL.set(username=role, password="secret")

    remedy = "\n".join(_remedy('FATAL:  role "x" does not exist', url=url))

    assert f'CREATE ROLE "{role}" WITH LOGIN CREATEDB PASSWORD' in remedy


def test_a_suggested_statement_names_a_role_the_way_the_command_would_and_carries_a_verifier() -> None:
    assert statement_value("user") == '"user"'
    assert password_value("pa'ss").startswith("'SCRAM-SHA-256$4096:")
    assert "pa'ss" not in password_value("pa'ss")


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
        anchor=ModuleSlotAnchor(
            occurrence=SampleOccurrence(module_hash="b" * 64, instrument_index=1, sample_slot=0),
            module_filename="song.xm",
            sample_name="kick",
        ),
        source=AnnotationSource.SAMPLE,
        annotated_at=datetime.now(UTC),
    )

    connection = connect(prepared_database_url)
    try:
        PostgresSampleAnnotationRepository(connection).upsert_many((annotation,))
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
    outcome = DatabaseOutcome(name="sampleripper", owner="sampleripper", created=False)

    assert (outcome.name, outcome.owner, outcome.created) == ("sampleripper", "sampleripper", False)


def test_advice_names_the_place_a_refused_connection_was_read_from() -> None:
    """A role rejected on the admin variable is not a role config.toml has anything to say about."""
    from_variable = "\n".join(
        _remedy(
            'FATAL:  password authentication failed for user "postgres"',
            source=ConnectionSource.ADMIN_VARIABLE,
        )
    )

    assert ADMIN_URL_ENVIRONMENT_VARIABLE in from_variable
    assert "your library's own database_url" in from_variable


def test_a_refused_admin_connection_is_never_told_to_set_the_variable_it_came_from() -> None:
    """The route already taken is the one route that cannot be the way out of taking it."""
    from_variable = "\n".join(
        _remedy(
            'FATAL:  password authentication failed for user "postgres"',
            source=ConnectionSource.ADMIN_VARIABLE,
        )
    )

    assert "CREATE ROLE" not in from_variable
    assert f"Set {ADMIN_URL_ENVIRONMENT_VARIABLE}" not in from_variable


def test_a_container_is_offered_wherever_no_superuser_can_be_reached() -> None:
    for source in ConnectionSource:
        remedy = "\n".join(_remedy('FATAL:  password authentication failed for user "x"', source=source))

        assert "docker compose up -d postgres" in remedy


def test_a_connection_url_says_what_to_put_in_it_before_showing_the_line() -> None:
    """A placeholder a person could paste unchanged is the trap this wording stays clear of."""
    remedy = "\n".join(_remedy('FATAL:  password authentication failed for user "sampleripper"'))

    assert "usually the `postgres`" in remedy
    assert "Replace <password> with that account's own" in remedy
    assert "<password>@localhost:5432/postgres" in remedy


def test_the_connection_source_follows_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ADMIN_URL_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.delenv(DATABASE_URL_ENVIRONMENT_VARIABLE, raising=False)
    assert connection_source() is ConnectionSource.CONFIGURATION

    monkeypatch.setenv(DATABASE_URL_ENVIRONMENT_VARIABLE, "postgresql+psycopg://someone:secret@localhost:5432/library")
    assert connection_source() is ConnectionSource.DATABASE_VARIABLE

    monkeypatch.setenv(ADMIN_URL_ENVIRONMENT_VARIABLE, "postgresql+psycopg://root:root@localhost:5432/postgres")
    assert connection_source() is ConnectionSource.ADMIN_VARIABLE


def test_an_empty_environment_variable_names_no_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ADMIN_URL_ENVIRONMENT_VARIABLE, "")
    monkeypatch.setenv(DATABASE_URL_ENVIRONMENT_VARIABLE, "")

    assert connection_source() is ConnectionSource.CONFIGURATION
    assert tuple(url.database for url in admin_urls(_LIBRARY_URL.render_as_string())) == MAINTENANCE_DATABASES


def test_a_configured_connection_is_described_by_the_file_it_came_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "sandbox.toml"
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))

    assert str(config_path) in describe_source(ConnectionSource.CONFIGURATION)


@dataclass(frozen=True)
class ServerCase:
    url: str
    described: str
    address: str


@pytest.mark.parametrize(
    "case",
    [
        ServerCase("postgresql+psycopg://someone:secret@db.test:5433/library", "db.test:5433", "db.test:5433"),
        ServerCase("postgresql+psycopg://someone:secret@db.test/library", "db.test:5432", "db.test:5432"),
        ServerCase("postgresql+psycopg://someone:secret@/library", "the local socket for port 5432", "localhost:5432"),
    ],
    ids=("host and port", "default port", "local socket"),
)
def test_a_server_is_named_the_way_the_driver_reaches_it(case: ServerCase) -> None:
    url = make_url(case.url)

    assert describe_server(url) == case.described
    assert server_address(url) == case.address


def test_a_rejected_password_offers_to_set_it_on_the_existing_role_through_its_verifier() -> None:
    """The statement gives the role the configured password while the advice itself never shows it."""
    remedy = "\n".join(_remedy('FATAL:  password authentication failed for user "sampleripper"'))

    assert 'ALTER ROLE "sampleripper" WITH PASSWORD \'SCRAM-SHA-256$4096:' in remedy
    assert _LIBRARY_URL.password not in remedy


def test_a_missing_role_is_offered_its_creation_alone() -> None:
    remedy = "\n".join(_remedy('FATAL:  role "sampleripper" does not exist'))

    assert "ALTER ROLE" not in remedy
    assert "CREATE ROLE" in remedy


def test_advice_for_a_url_without_a_port_names_a_connection_url_that_parses() -> None:
    url = make_url("postgresql+psycopg://sampleripper:not-a-real-password@localhost/sampleripper")

    remedy = _remedy('FATAL:  password authentication failed for user "sampleripper"', url=url)

    admin_line = next(line.strip() for line in remedy if "<password>@" in line)
    assert make_url(admin_line).port == 5432


def test_provisioning_creates_service_roles_that_log_in_holding_what_their_service_needs(
    module_cluster_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A server of a person's own, played by a library's own cluster, whose owner is the superuser `provision` asks."""
    superuser = make_url(managed_catalog_url(module_cluster_root))
    monkeypatch.setenv(
        ADMIN_URL_ENVIRONMENT_VARIABLE,
        superuser.set(database=MAINTENANCE_DATABASES[0]).render_as_string(hide_password=False),
    )
    owner = superuser.set(username="provisioned_owner", password="owner-secret", database="provisioned")
    service_urls = {
        ServiceRole.READER: owner.set(username="provisioned_reader", password="reader-secret"),
        ServiceRole.CURATOR: owner.set(username="provisioned_curator", password="curator-secret"),
    }
    rendered = {service: url.render_as_string(hide_password=False) for service, url in service_urls.items()}

    first = provision(owner.render_as_string(hide_password=False), service_urls=rendered)
    again = provision(owner.render_as_string(hide_password=False), service_urls=rendered)

    assert first.service_roles_created == ("provisioned_reader", "provisioned_curator")
    assert again.service_roles_created == ()
    assert again.service_roles == ("provisioned_reader", "provisioned_curator")
