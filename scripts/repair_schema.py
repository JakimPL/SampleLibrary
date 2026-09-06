from __future__ import annotations

import argparse
import logging
from typing import Final

from sqlalchemy import Connection, text

from samplecore.cli_support import bootstrap_cli, confirmed, open_catalog_connection
from samplecore.storage.database import create_schema, metadata

_BACKUP_SUFFIX: Final[str] = "__schema_repair_backup"

_logger = logging.getLogger(__name__)


class SchemaRepairError(RuntimeError):
    """A repair step did not come out with the same row counts it started from."""


def repair_schema(connection: Connection) -> None:
    """Rebuild every catalog table against the code's current definitions, preserving every row.

    DuckDB has no ``ALTER TABLE ... {ADD,DROP} CONSTRAINT`` for a CHECK constraint (confirmed
    against duckdb 1.5.5), so a table whose constraint changed after the table already existed --
    for example ``module.tracker`` gaining ``'mod'``/``'s3m'`` -- keeps enforcing its original,
    stale constraint indefinitely, even though ``connect()`` calls ``create_schema`` on every
    startup: ``metadata.create_all`` only creates a table that does not exist yet, never alters one
    that already does. This backs up every row, drops every table, recreates the whole schema fresh
    from today's definitions, and reloads every row -- verifying counts against the backups before
    the backups are removed, and again after reload before anything is dropped.

    Raises:
        SchemaRepairError: a backup or a reload did not come out with the same row count as its
            source. Backup tables are left in place, named ``{table}__schema_repair_backup``, for
            manual recovery.
    """
    table_names = [table.name for table in metadata.sorted_tables]
    row_counts_before = {name: _row_count(connection, name) for name in table_names}

    _logger.info("Backing up %d tables (%d rows total)...", len(table_names), sum(row_counts_before.values()))
    _backup_every_table(connection, table_names)
    _verify_row_counts(
        connection, {_backup_name(name): count for name, count in row_counts_before.items()}, step="backup"
    )

    _logger.info("Dropping and recreating the schema...")
    for name in reversed(table_names):
        connection.execute(text(f'DROP TABLE "{name}"'))
    connection.commit()

    create_schema(connection)
    connection.commit()

    _logger.info("Reloading every table from its backup...")
    _reload_every_table(connection, table_names)
    _verify_row_counts(connection, row_counts_before, step="reload")

    _logger.info("Removing backup tables...")
    _drop_every_backup(connection, table_names)


def _backup_name(table_name: str) -> str:
    return f"{table_name}{_BACKUP_SUFFIX}"


def _row_count(connection: Connection, table_name: str) -> int:
    return int(connection.execute(text(f'SELECT count(*) FROM "{table_name}"')).scalar_one())


def _backup_every_table(connection: Connection, table_names: list[str]) -> None:
    for name in table_names:
        connection.execute(text(f'CREATE TABLE "{_backup_name(name)}" AS SELECT * FROM "{name}"'))
    connection.commit()


def _reload_every_table(connection: Connection, table_names: list[str]) -> None:
    for name in table_names:
        connection.execute(text(f'INSERT INTO "{name}" SELECT * FROM "{_backup_name(name)}"'))
    connection.commit()


def _drop_every_backup(connection: Connection, table_names: list[str]) -> None:
    for name in table_names:
        connection.execute(text(f'DROP TABLE "{_backup_name(name)}"'))
    connection.commit()


def _verify_row_counts(connection: Connection, expected_by_table: dict[str, int], *, step: str) -> None:
    for table_name, expected_count in expected_by_table.items():
        actual_count = _row_count(connection, table_name)
        if actual_count != expected_count:
            raise SchemaRepairError(
                f"{step} step left {table_name!r} with {actual_count} rows, expected {expected_count}. "
                "Nothing past this point was touched; backup tables are left in place for recovery."
            )


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild every catalog table against the code's current schema, preserving every "
        "row. Needed when a table's constraint changed after the table was first created, since "
        "create_schema() only creates a table that does not exist yet and never alters one that does."
    )
    parser.add_argument(
        "--confirm", action="store_true", help="Actually perform the repair. Without this flag, nothing is changed."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    if not confirmed(
        argv,
        _parse_arguments,
        "This would back up, drop, and recreate every table in the configured library's catalog, "
        "then reload every row -- fixing any table stuck on a stale constraint from before a "
        "schema change.",
    ):
        return

    config = bootstrap_cli()
    _logger.info("Repairing the schema at %s...", config.resolved_database_path)
    with open_catalog_connection(config.resolved_database_path) as connection:
        repair_schema(connection)

    _logger.info("Done. Every table now matches the current schema; every row survived.")


if __name__ == "__main__":
    main()
