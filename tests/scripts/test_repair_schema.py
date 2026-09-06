from __future__ import annotations

import importlib.util
import types
from pathlib import Path

import pytest
from sqlalchemy import (
    CheckConstraint,
    Column,
    Connection,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    Sequence,
    String,
    Table,
    create_engine,
    func,
    select,
    text,
)
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

from samplecore.storage.database import connect, create_schema, metadata
from samplecore.storage.repositories.module import DuckDBModuleRepository
from samplecore.storage.types import TinyInt, UBigInt, UInteger, USmallInt, UTinyInt

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "repair_schema.py"


def _load_script(path: Path, name: str) -> types.ModuleType:
    """Imports a script by file path -- it lives outside every installed package, by design."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


repair_schema_script = _load_script(_SCRIPT_PATH, "repair_schema")


def _row_counts(connection: Connection) -> dict[str, int]:
    return {
        table.name: connection.execute(select(func.count()).select_from(table)).scalar_one()
        for table in metadata.sorted_tables
    }


def _build_stale_module_and_sample_properties(connection: Connection) -> None:
    """Creates ``module``/``sample_properties``/``xm_sample_properties`` with the tracker CHECK
    constraint as it read before MOD/S3M support existed -- reproducing a real catalog created
    before that schema change, where the constraint text on an already-existing table never
    updates on its own.
    """
    stale_metadata = MetaData()
    module_id_sequence = Sequence("module_id_seq")
    Table(
        "module",
        stale_metadata,
        Column("id", Integer, module_id_sequence, primary_key=True, server_default=module_id_sequence.next_value()),
        Column("hash", String(64), nullable=False, unique=True),
        Column("filename", String, nullable=False),
        Column("tracker", String, nullable=False),
        Column("title", String, nullable=False),
        Column("channel_count", USmallInt, nullable=False),
        Column("pattern_count", USmallInt, nullable=False),
        Column("instrument_count", USmallInt, nullable=False),
        Column("sample_count", USmallInt, nullable=False),
        Column("file_size", UBigInt, nullable=False),
        Column("ingested_at", DateTime(timezone=True), nullable=False),
        CheckConstraint("tracker IN ('xm', 'it')", name="module_tracker_check"),
    )
    Table(
        "sample",
        stale_metadata,
        Column("hash", String(64), primary_key=True),
        Column("depth", UTinyInt, nullable=False),
        Column("channels", UTinyInt, nullable=False),
        Column("frames", UInteger, nullable=False),
    )
    Table(
        "sample_properties",
        stale_metadata,
        Column("module_id", Integer, ForeignKey("module.id"), nullable=False),
        Column("instrument_index", USmallInt, nullable=False),
        Column("sample_slot", USmallInt, nullable=False),
        Column("sample_hash", String(64), ForeignKey("sample.hash"), nullable=False),
        Column("tracker", String, nullable=False),
        Column("name", String, nullable=False),
        Column("rate", UInteger, nullable=False),
        Column("volume", UTinyInt, nullable=False),
        Column("panning", UTinyInt, nullable=True),
        Column("loop_begin", UInteger, nullable=True),
        Column("loop_end", UInteger, nullable=True),
        Column("loop_mode", String, nullable=True),
        PrimaryKeyConstraint("module_id", "instrument_index", "sample_slot"),
        CheckConstraint("tracker IN ('xm', 'it')", name="sample_properties_tracker_check"),
    )
    Table(
        "xm_sample_properties",
        stale_metadata,
        Column("module_id", Integer, nullable=False),
        Column("instrument_index", USmallInt, nullable=False),
        Column("sample_slot", USmallInt, nullable=False),
        Column("relative_note", TinyInt, nullable=False),
        Column("finetune", TinyInt, nullable=False),
        PrimaryKeyConstraint("module_id", "instrument_index", "sample_slot"),
        ForeignKeyConstraint(
            ["module_id", "instrument_index", "sample_slot"],
            ["sample_properties.module_id", "sample_properties.instrument_index", "sample_properties.sample_slot"],
        ),
    )
    stale_metadata.create_all(connection)
    connection.commit()


def _stale_library(tmp_path: Path) -> Connection:
    # The stale tables must exist before create_schema ever runs against this file -- create_schema
    # (which connect() would otherwise call first) only creates a table that does not exist yet, so
    # calling connect() before the stale tables exist would create them with today's constraint
    # instead of reproducing one written before the constraint changed.
    engine = create_engine(URL.create(drivername="duckdb", database=str(tmp_path / "samplelibrary.duckdb")))
    connection = engine.connect()
    _build_stale_module_and_sample_properties(connection)
    # Mirrors what already happened to a real catalog: every connect() since made fills in whatever
    # table does not exist yet, leaving only module/sample_properties on the stale constraint.
    create_schema(connection)
    connection.commit()

    for index in range(3):
        module_id = connection.execute(text("SELECT nextval('module_id_seq')")).scalar_one()
        connection.execute(
            text("INSERT INTO module VALUES (:id, :hash, 'file.xm', 'xm', 'title', 4, 1, 1, 1, 100, now())"),
            {"id": module_id, "hash": format(index, "064x")},
        )
        connection.execute(
            text("INSERT INTO sample VALUES (:hash, 16, 1, 1000)"), {"hash": format(index + 100, "064x")}
        )
        connection.execute(
            text(
                "INSERT INTO sample_properties VALUES (:id, 0, 0, :sample_hash, 'xm', 'kick', 8363, 64, "
                "NULL, NULL, NULL, NULL)"
            ),
            {"id": module_id, "sample_hash": format(index + 100, "064x")},
        )
        connection.execute(text("INSERT INTO xm_sample_properties VALUES (:id, 0, 0, 0, 0)"), {"id": module_id})
    connection.commit()

    return connection


def test_repair_schema_preserves_every_row_while_fixing_a_stale_constraint(tmp_path: Path) -> None:
    connection = _stale_library(tmp_path)
    before = _row_counts(connection)
    assert before["module"] == 3
    with pytest.raises(IntegrityError, match="CHECK constraint failed"):
        connection.execute(
            text("INSERT INTO module VALUES (999, 'modhash', 'file.mod', 'mod', 'title', 4, 1, 1, 1, 100, now())")
        )
    connection.rollback()

    repair_schema_script.repair_schema(connection)

    after = _row_counts(connection)
    assert after == before
    connection.execute(
        text("INSERT INTO module VALUES (999, :hash, 'file.mod', 'mod', 'title', 4, 1, 1, 1, 100, now())"),
        {"hash": format(999, "064x")},
    )
    connection.commit()
    assert connection.execute(select(func.count()).select_from(metadata.tables["module"])).scalar_one() == 4


def test_repair_schema_does_not_collide_the_module_id_sequence_with_reloaded_rows(tmp_path: Path) -> None:
    connection = _stale_library(tmp_path)

    repair_schema_script.repair_schema(connection)

    next_id = DuckDBModuleRepository(connection).next_id()
    existing_ids = {row[0] for row in connection.execute(text("SELECT id FROM module")).fetchall()}
    assert next_id not in existing_ids


def test_repair_schema_is_a_harmless_no_op_on_an_already_current_schema(tmp_path: Path) -> None:
    connection = connect(tmp_path / "samplelibrary.duckdb")
    connection.commit()
    before = _row_counts(connection)

    repair_schema_script.repair_schema(connection)

    assert _row_counts(connection) == before


def test_verify_row_counts_raises_on_a_mismatch(tmp_path: Path) -> None:
    connection = connect(tmp_path / "samplelibrary.duckdb")
    connection.commit()

    with pytest.raises(repair_schema_script.SchemaRepairError, match="module"):
        repair_schema_script._verify_row_counts(connection, {"module": 1}, step="backup")


def test_confirm_flag_defaults_to_false() -> None:
    arguments = repair_schema_script._parse_arguments([])

    assert arguments.confirm is False


def test_confirm_flag_can_be_set() -> None:
    arguments = repair_schema_script._parse_arguments(["--confirm"])

    assert arguments.confirm is True


def test_main_without_confirm_changes_nothing(tmp_path: Path) -> None:
    connection = _stale_library(tmp_path)
    before = _row_counts(connection)
    connection.close()

    repair_schema_script.main([])

    after_connection = connect(tmp_path / "samplelibrary.duckdb")
    after = _row_counts(after_connection)
    after_connection.close()
    assert after == before
