from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Connection, inspect
from sqlalchemy.exc import OperationalError

from samplecore.storage.database import connect, create_schema

EXPECTED_TABLES = frozenset(
    {"sample", "module", "sample_properties", "xm_sample_properties", "it_sample_properties", "sample_relation"}
)


def test_create_schema_creates_every_expected_table(connection: Connection) -> None:
    tables = set(inspect(connection).get_table_names())

    assert EXPECTED_TABLES <= tables


def test_create_schema_is_idempotent(connection: Connection) -> None:
    create_schema(connection)
    create_schema(connection)


def test_connect_creates_the_schema_in_a_fresh_database_file(tmp_path: Path) -> None:
    database_path = tmp_path / "library.duckdb"

    connection = connect(database_path)
    try:
        tables = set(inspect(connection).get_table_names())
    finally:
        connection.close()

    assert database_path.is_file()
    assert EXPECTED_TABLES <= tables


def test_a_read_only_connection_to_a_missing_database_fails_rather_than_creating_one(tmp_path: Path) -> None:
    database_path = tmp_path / "does-not-exist.duckdb"

    with pytest.raises(OperationalError):
        connect(database_path, read_only=True)

    assert not database_path.is_file()
