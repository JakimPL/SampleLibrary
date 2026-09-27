from __future__ import annotations

from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pytest
from psycopg import errors as postgres_errors
from sqlalchemy import Connection, create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

from samplecore.models.annotation import AnnotationSource, SampleAnnotation, SampleFileAnchor
from samplecore.models.sample_file import SampleFileLocation
from samplecore.models.service_role import ServiceRole
from samplecore.storage.cluster.embedded.state import (
    MANAGED_DATABASE,
    managed_catalog_url,
    managed_role_name,
    managed_service_url,
)
from samplecore.storage.cluster.statements import create_service_role
from samplecore.storage.curation import annotation_history
from samplecore.storage.database import connect
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository
from samplecore.storage.service_roles import ServiceRoleRefusedError, check_service_role, grant_service_role

EMPTY_DATABASE: Final[str] = "not_a_catalog"


@dataclass(frozen=True)
class RefusedStatement:
    service: ServiceRole
    statement: str


REFUSED_STATEMENTS: Final[tuple[RefusedStatement, ...]] = (
    RefusedStatement(ServiceRole.READER, "INSERT INTO public.module DEFAULT VALUES"),
    RefusedStatement(ServiceRole.READER, "UPDATE public.sample SET frames = 0"),
    RefusedStatement(ServiceRole.READER, "DELETE FROM public.sample"),
    RefusedStatement(ServiceRole.READER, "TRUNCATE public.sample CASCADE"),
    RefusedStatement(ServiceRole.READER, "CREATE TABLE public.intruder (id integer)"),
    RefusedStatement(ServiceRole.READER, "CREATE SCHEMA intruder"),
    RefusedStatement(ServiceRole.READER, "DELETE FROM curation.sample_annotation"),
    RefusedStatement(ServiceRole.READER, "INSERT INTO curation.tag_rank VALUES ('KICK', 0)"),
    RefusedStatement(ServiceRole.READER, "SELECT * FROM curation.annotation_history"),
    RefusedStatement(ServiceRole.READER, "SELECT nextval('public.module_id_seq')"),
    RefusedStatement(ServiceRole.READER, "CREATE TEMPORARY TABLE intruder (id integer)"),
    RefusedStatement(ServiceRole.READER, "SELECT pg_catalog.pg_read_file('postgresql.conf')"),
    RefusedStatement(ServiceRole.READER, "SET ROLE samplelibrary"),
    RefusedStatement(ServiceRole.CURATOR, "TRUNCATE curation.sample_annotation"),
    RefusedStatement(ServiceRole.CURATOR, "UPDATE public.sample SET frames = 0"),
    RefusedStatement(ServiceRole.CURATOR, "DELETE FROM public.module"),
    RefusedStatement(ServiceRole.CURATOR, "UPDATE curation.tag_rank SET rank = 0"),
    RefusedStatement(ServiceRole.CURATOR, "DELETE FROM curation.tag_rank"),
    RefusedStatement(ServiceRole.CURATOR, "SELECT * FROM curation.annotation_history"),
    RefusedStatement(ServiceRole.CURATOR, "DELETE FROM curation.annotation_history"),
    RefusedStatement(
        ServiceRole.CURATOR, "INSERT INTO curation.annotation_history (sample_hash, operation) VALUES ('a', 'insert')"
    ),
    RefusedStatement(ServiceRole.CURATOR, "INSERT INTO curation.annotation_import VALUES ('a', 1, now())"),
    RefusedStatement(ServiceRole.CURATOR, "ALTER TABLE curation.sample_annotation DISABLE TRIGGER ALL"),
    RefusedStatement(ServiceRole.CURATOR, "DROP TRIGGER sample_annotation_history ON curation.sample_annotation"),
    RefusedStatement(ServiceRole.CURATOR, "SET session_replication_role = replica"),
    RefusedStatement(ServiceRole.CURATOR, "CREATE TABLE curation.intruder (id integer)"),
    RefusedStatement(ServiceRole.CURATOR, "SELECT nextval('public.module_id_seq')"),
    RefusedStatement(ServiceRole.CURATOR, "CREATE TEMPORARY TABLE intruder (id integer)"),
)
PROBE_ROLE: Final[str] = "membership_probe"
PROBE_PASSWORD: Final[str] = "a-password-for-the-probe-role-alone"
GRANTED_GROUP: Final[str] = "pg_read_server_files"


@pytest.fixture
def owner(module_cluster_root: Path) -> Iterator[Connection]:
    with closing(connect(managed_catalog_url(module_cluster_root))) as connection:
        yield connection


def _connected_as(root: Path, service: ServiceRole) -> closing[Connection]:
    return closing(create_engine(managed_service_url(root, service), poolclass=NullPool).connect())


@pytest.mark.parametrize(
    "refused", REFUSED_STATEMENTS, ids=lambda refused: f"{refused.service.value}: {refused.statement}"
)
def test_a_service_role_is_refused_everything_past_its_service(
    module_cluster_root: Path, refused: RefusedStatement
) -> None:
    with _connected_as(module_cluster_root, refused.service) as connection:
        with pytest.raises(ProgrammingError) as refusal:
            connection.execute(text(refused.statement))

    assert isinstance(refusal.value.orig, postgres_errors.InsufficientPrivilege)


def test_a_curator_records_labels_and_the_history_names_it(module_cluster_root: Path, owner: Connection) -> None:
    sample_hash = "d" * 64
    annotation = SampleAnnotation(
        sample_hash=sample_hash,
        label="KICK",
        rating=None,
        favorite=False,
        anchor=SampleFileAnchor(location=SampleFileLocation(directory="/samples", relative_path="kick.wav")),
        source=AnnotationSource.SAMPLE,
        annotated_at=datetime.now(UTC),
    )
    with _connected_as(module_cluster_root, ServiceRole.CURATOR) as connection:
        PostgresSampleAnnotationRepository(connection).upsert_many((annotation,))
        connection.commit()

    roles = owner.execute(
        select(annotation_history.c.role).where(annotation_history.c.sample_hash == sample_hash)
    ).scalars()
    assert list(roles) == [managed_role_name(ServiceRole.CURATOR)]


@pytest.mark.parametrize("service", list(ServiceRole))
def test_each_service_role_holds_exactly_what_its_service_needs(
    module_cluster_root: Path, service: ServiceRole
) -> None:
    with _connected_as(module_cluster_root, service) as connection:
        check_service_role(connection, service)


def test_a_curator_is_refused_as_a_reader(module_cluster_root: Path) -> None:
    with _connected_as(module_cluster_root, ServiceRole.CURATOR) as connection:
        with pytest.raises(ServiceRoleRefusedError, match="may INSERT on curation.sample_annotation"):
            check_service_role(connection, ServiceRole.READER)


def test_the_catalogs_owner_is_refused_as_a_reader(owner: Connection) -> None:
    with pytest.raises(ServiceRoleRefusedError, match="is a superuser") as refusal:
        check_service_role(owner, ServiceRole.READER)

    assert any("it owns table public.sample" in problem for problem in refusal.value.problems)


def test_a_database_holding_no_catalog_is_named_unprepared(module_cluster_root: Path, owner: Connection) -> None:
    administrator = create_engine(managed_catalog_url(module_cluster_root), isolation_level="AUTOCOMMIT")
    with administrator.connect() as connection:
        connection.execute(text(f"DROP DATABASE IF EXISTS {EMPTY_DATABASE}"))
        connection.execute(text(f"CREATE DATABASE {EMPTY_DATABASE}"))
    administrator.dispose()
    url = make_url(managed_service_url(module_cluster_root, ServiceRole.READER)).set(database=EMPTY_DATABASE)

    with closing(create_engine(url, poolclass=NullPool).connect()) as connection:
        with pytest.raises(ServiceRoleRefusedError, match="the catalog isn't prepared"):
            check_service_role(connection, ServiceRole.READER)


def test_a_role_belonging_to_another_role_is_refused_naming_it(module_cluster_root: Path, owner: Connection) -> None:
    """Membership hands over the group's rights, reading the server's files among them for this group."""
    administrator = create_engine(managed_catalog_url(module_cluster_root), isolation_level="AUTOCOMMIT")
    with administrator.connect() as connection:
        create_service_role(connection, role=PROBE_ROLE, password=PROBE_PASSWORD)
        connection.execute(text(f"GRANT {GRANTED_GROUP} TO {PROBE_ROLE}"))
    grant_service_role(owner, service=ServiceRole.READER, role=PROBE_ROLE)
    owner.commit()
    url = make_url(managed_catalog_url(module_cluster_root)).set(username=PROBE_ROLE, password=PROBE_PASSWORD)
    try:
        with closing(create_engine(url, poolclass=NullPool).connect()) as connection:
            with pytest.raises(ServiceRoleRefusedError, match=f"it belongs to role {GRANTED_GROUP}"):
                check_service_role(connection, ServiceRole.READER)
    finally:
        with administrator.connect() as connection:
            connection.execute(text(f"DROP OWNED BY {PROBE_ROLE}"))
            connection.execute(text(f"DROP ROLE {PROBE_ROLE}"))
        administrator.dispose()


def test_a_database_left_open_to_everyone_is_refused_for_its_temporary_tables(
    module_cluster_root: Path, owner: Connection
) -> None:
    """Postgres lets every role create temporary tables in a new database until that right is taken away."""
    owner.execute(text(f"GRANT TEMPORARY ON DATABASE {MANAGED_DATABASE} TO PUBLIC"))
    owner.commit()
    try:
        with _connected_as(module_cluster_root, ServiceRole.READER) as connection:
            with pytest.raises(ServiceRoleRefusedError, match="it may create temporary tables"):
                check_service_role(connection, ServiceRole.READER)
    finally:
        owner.execute(text(f"REVOKE TEMPORARY ON DATABASE {MANAGED_DATABASE} FROM PUBLIC"))
        owner.commit()
