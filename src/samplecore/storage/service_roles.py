from __future__ import annotations

from typing import Final

from sqlalchemy import Connection, text

from samplecore.models.service_role import ServiceRole
from samplecore.storage.curation import CURATION_SCHEMA, sample_annotation, tag_rank
from samplecore.storage.database import claim_schema_creation, metadata

PUBLIC_SCHEMA: Final[str] = "public"
SERVED_SCHEMAS: Final[tuple[str, ...]] = (PUBLIC_SCHEMA, CURATION_SCHEMA)
WRITE_PRIVILEGES: Final[tuple[str, ...]] = ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
SEQUENCE_PRIVILEGES: Final[tuple[str, ...]] = ("USAGE", "UPDATE")
ROLE_POWERS: Final[dict[str, str]] = {
    "rolsuper": "is a superuser",
    "rolcreaterole": "may create roles",
    "rolcreatedb": "may create databases",
    "rolbypassrls": "bypasses row security",
    "rolreplication": "may replicate the server",
}
CURATION_WRITES: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        (f"{CURATION_SCHEMA}.{sample_annotation.name}", "INSERT"),
        (f"{CURATION_SCHEMA}.{sample_annotation.name}", "UPDATE"),
        (f"{CURATION_SCHEMA}.{sample_annotation.name}", "DELETE"),
        (f"{CURATION_SCHEMA}.{tag_rank.name}", "INSERT"),
    }
)
SERVED_CURATION_TABLES: Final[tuple[str, ...]] = (
    f"{CURATION_SCHEMA}.{sample_annotation.name}",
    f"{CURATION_SCHEMA}.{tag_rank.name}",
)


def permitted_writes(service: ServiceRole) -> frozenset[tuple[str, str]]:
    """The tables a role of ``service`` may write and how, each as its qualified name and a privilege."""
    match service:
        case ServiceRole.READER:
            return frozenset()
        case ServiceRole.CURATOR:
            return CURATION_WRITES


class ServiceRoleRefusedError(Exception):
    """Raised when the role a served catalog API connects as may do more, or less, than its service needs.

    ``problems`` names each difference, ready to print on a line of its own.
    """

    def __init__(self, service: ServiceRole, role: str, problems: tuple[str, ...]) -> None:
        super().__init__(f"Role {role!r} doesn't fit a {service.value}: {'; '.join(problems)}.")
        self.problems = problems


def grant_service_role(connection: Connection, *, service: ServiceRole, role: str) -> None:
    """Grant ``role`` what ``service`` needs on the catalog this connection opens, run by the catalog's owner.

    Every catalog table is readable, and so are the tables later created by the owner, and a curator
    may write labels and new tag ranks. Nothing else is granted: no other table, no sequence, and
    nothing on the label history, which its trigger writes with the owner's rights. Postgres lets
    every role connect to a new database and create temporary tables in it, so both go from
    ``PUBLIC``, and the role is granted the connection alone. Granting runs under the schema lock,
    which keeps several processes preparing one catalog from colliding.
    """
    preparer = connection.dialect.identifier_preparer
    quoted = preparer.quote(role)
    database = preparer.quote(str(connection.execute(text("SELECT current_database()")).scalar_one()))
    statements = [
        f"REVOKE TEMPORARY, CONNECT ON DATABASE {database} FROM PUBLIC",
        f"GRANT CONNECT ON DATABASE {database} TO {quoted}",
        f"GRANT USAGE ON SCHEMA {', '.join(SERVED_SCHEMAS)} TO {quoted}",
        f"GRANT SELECT ON ALL TABLES IN SCHEMA {PUBLIC_SCHEMA} TO {quoted}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {PUBLIC_SCHEMA} GRANT SELECT ON TABLES TO {quoted}",
        f"GRANT SELECT ON {', '.join(SERVED_CURATION_TABLES)} TO {quoted}",
    ]
    for table, privilege in sorted(permitted_writes(service)):
        statements.append(f"GRANT {privilege} ON {table} TO {quoted}")
    claim_schema_creation(connection)
    for statement in statements:
        connection.execute(text(statement))


def check_service_role(connection: Connection, service: ServiceRole) -> None:
    """Insist that the role this connection logs in as holds exactly what ``service`` needs, and nothing more.

    The role has no power over the server, belongs to no other role, owns nothing, may create
    nothing, temporary tables included, reads every table the catalog API reads, and writes exactly
    the tables and privileges its service permits.

    Raises:
        ServiceRoleRefusedError: the role differs from that, naming each difference.
    """
    role = str(connection.execute(text("SELECT current_user")).scalar_one())
    problems = (
        *_powers(connection),
        *_memberships(connection),
        *_ownership(connection),
        *_creation(connection),
        *_writes(connection, service),
        *_reads(connection),
    )
    if problems:
        raise ServiceRoleRefusedError(service, role, problems)


def _powers(connection: Connection) -> tuple[str, ...]:
    row = connection.execute(
        text(f"SELECT {', '.join(ROLE_POWERS)} FROM pg_catalog.pg_roles WHERE rolname = current_user")
    ).one()
    return tuple(f"it {description}" for description, held in zip(ROLE_POWERS.values(), row, strict=True) if held)


def _memberships(connection: Connection) -> tuple[str, ...]:
    """The roles this one belongs to, whose rights it holds too, the predefined ones included."""
    groups = connection.execute(
        text(
            "SELECT granted.rolname FROM pg_catalog.pg_auth_members AS membership "
            "JOIN pg_catalog.pg_roles AS granted ON granted.oid = membership.roleid "
            "JOIN pg_catalog.pg_roles AS member ON member.oid = membership.member "
            "WHERE member.rolname = current_user ORDER BY granted.rolname"
        )
    ).scalars()
    return tuple(f"it belongs to role {name}" for name in groups)


def _ownership(connection: Connection) -> tuple[str, ...]:
    owned = connection.execute(
        text(
            "SELECT 'database ' || datname FROM pg_catalog.pg_database "
            "WHERE datname = current_database() AND pg_has_role(datdba, 'MEMBER') "
            "UNION ALL SELECT 'schema ' || nspname FROM pg_catalog.pg_namespace "
            "WHERE nspname = ANY(:schemas) AND pg_has_role(nspowner, 'MEMBER') "
            "UNION ALL SELECT 'table ' || n.nspname || '.' || c.relname FROM pg_catalog.pg_class AS c "
            "JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace "
            "WHERE n.nspname = ANY(:schemas) AND pg_has_role(c.relowner, 'MEMBER')"
        ),
        {"schemas": list(SERVED_SCHEMAS)},
    ).scalars()
    return tuple(f"it owns {name}" for name in owned)


def _creation(connection: Connection) -> tuple[str, ...]:
    places = connection.execute(
        text(
            "SELECT 'objects in database ' || current_database() "
            "WHERE has_database_privilege(current_database(), 'CREATE') "
            "UNION ALL SELECT 'temporary tables in database ' || current_database() "
            "WHERE has_database_privilege(current_database(), 'TEMPORARY') "
            "UNION ALL SELECT 'objects in schema ' || nspname FROM pg_catalog.pg_namespace "
            "WHERE nspname = ANY(:schemas) AND has_schema_privilege(nspname, 'CREATE')"
        ),
        {"schemas": list(SERVED_SCHEMAS)},
    ).scalars()
    return tuple(f"it may create {place}" for place in places)


def _writes(connection: Connection, service: ServiceRole) -> tuple[str, ...]:
    """The writes the role holds past its service, and the ones its service needs that it lacks."""
    held = {
        (str(row.name), str(row.privilege))
        for row in connection.execute(
            text(
                "SELECT n.nspname || '.' || c.relname AS name, privilege FROM pg_catalog.pg_class AS c "
                "JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace "
                "CROSS JOIN unnest(CAST(:privileges AS text[])) AS privilege "
                "WHERE n.nspname = ANY(:schemas) AND c.relkind IN ('r', 'p', 'v', 'm') "
                "AND has_table_privilege(c.oid, privilege) "
                "UNION ALL SELECT n.nspname || '.' || c.relname, privilege FROM pg_catalog.pg_class AS c "
                "JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace "
                "CROSS JOIN unnest(CAST(:sequence_privileges AS text[])) AS privilege "
                "WHERE n.nspname = ANY(:schemas) AND c.relkind = 'S' AND has_sequence_privilege(c.oid, privilege)"
            ),
            {
                "privileges": list(WRITE_PRIVILEGES),
                "sequence_privileges": list(SEQUENCE_PRIVILEGES),
                "schemas": list(SERVED_SCHEMAS),
            },
        )
    }
    beyond = sorted(held - permitted_writes(service))
    lacking = sorted(permitted_writes(service) - held)
    return (
        *(f"it may {privilege} on {table}" for table, privilege in beyond),
        *(f"it may not {privilege} on {table}, which its service needs" for table, privilege in lacking),
    )


def _reads(connection: Connection) -> tuple[str, ...]:
    """The tables the catalog API reads that are missing, or that the role may not read."""
    tables = (*(f"{PUBLIC_SCHEMA}.{table.name}" for table in metadata.sorted_tables), *SERVED_CURATION_TABLES)
    rows = connection.execute(
        text(
            "SELECT name, to_regclass(name) IS NOT NULL AS present, "
            "to_regclass(name) IS NOT NULL AND has_table_privilege(to_regclass(name), 'SELECT') AS readable "
            "FROM unnest(CAST(:tables AS text[])) AS name"
        ),
        {"tables": list(tables)},
    ).fetchall()
    missing = [str(row.name) for row in rows if not row.present]
    if missing:
        return (f"the catalog isn't prepared: {', '.join(missing)} missing",)
    return tuple(f"it may not read {row.name}" for row in rows if not row.readable)
