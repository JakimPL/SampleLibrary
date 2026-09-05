from __future__ import annotations

from pathlib import Path
from typing import Final

import duckdb

_SCHEMA_STATEMENTS: Final[tuple[str, ...]] = (
    "CREATE SEQUENCE IF NOT EXISTS module_id_seq START 1",
    "CREATE SEQUENCE IF NOT EXISTS sample_relation_id_seq START 1",
    """
    CREATE TABLE IF NOT EXISTS sample (
        hash        VARCHAR(64) PRIMARY KEY,
        depth       UTINYINT NOT NULL CHECK (depth IN (8, 16)),
        channels    UTINYINT NOT NULL CHECK (channels IN (1, 2)),
        frames      UINTEGER NOT NULL CHECK (frames > 0)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS module (
        id                INTEGER PRIMARY KEY DEFAULT nextval('module_id_seq'),
        hash              VARCHAR(64) NOT NULL UNIQUE,
        filename          VARCHAR NOT NULL CHECK (filename NOT LIKE '%/%' AND filename NOT LIKE '%\\%'),
        tracker           VARCHAR NOT NULL CHECK (tracker IN ('xm', 'it')),
        title             VARCHAR NOT NULL,
        channel_count     USMALLINT NOT NULL,
        pattern_count     USMALLINT NOT NULL,
        instrument_count  USMALLINT NOT NULL,
        sample_count      USMALLINT NOT NULL,
        file_size         UBIGINT NOT NULL,
        ingested_at       TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sample_properties (
        module_id         INTEGER NOT NULL REFERENCES module(id),
        instrument_index  USMALLINT NOT NULL,
        sample_slot       USMALLINT NOT NULL,
        sample_hash       VARCHAR(64) NOT NULL REFERENCES sample(hash),
        tracker           VARCHAR NOT NULL CHECK (tracker IN ('xm', 'it')),
        name              VARCHAR NOT NULL,
        rate              UINTEGER NOT NULL CHECK (rate > 0),
        volume            UTINYINT NOT NULL CHECK (volume <= 64),
        panning           UTINYINT CHECK (panning <= 255),
        loop_begin        UINTEGER,
        loop_end          UINTEGER,
        loop_mode         VARCHAR CHECK (loop_mode IN ('forward', 'ping_pong')),
        PRIMARY KEY (module_id, instrument_index, sample_slot),
        CHECK ((loop_begin IS NULL) = (loop_end IS NULL) AND (loop_begin IS NULL) = (loop_mode IS NULL))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS xm_sample_properties (
        module_id         INTEGER NOT NULL,
        instrument_index  USMALLINT NOT NULL,
        sample_slot       USMALLINT NOT NULL,
        relative_note     TINYINT NOT NULL,
        finetune          TINYINT NOT NULL,
        PRIMARY KEY (module_id, instrument_index, sample_slot),
        FOREIGN KEY (module_id, instrument_index, sample_slot)
            REFERENCES sample_properties (module_id, instrument_index, sample_slot)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS it_sample_properties (
        module_id         INTEGER NOT NULL,
        instrument_index  USMALLINT NOT NULL,
        sample_slot       USMALLINT NOT NULL,
        global_volume     UTINYINT NOT NULL CHECK (global_volume <= 64),
        sustain_begin     UINTEGER,
        sustain_end       UINTEGER,
        sustain_mode      VARCHAR CHECK (sustain_mode IN ('forward', 'ping_pong')),
        filename          VARCHAR,
        vibrato_speed     UTINYINT,
        vibrato_depth     UTINYINT,
        vibrato_rate      UTINYINT,
        vibrato_waveform  UTINYINT,
        PRIMARY KEY (module_id, instrument_index, sample_slot),
        FOREIGN KEY (module_id, instrument_index, sample_slot)
            REFERENCES sample_properties (module_id, instrument_index, sample_slot),
        CHECK ((sustain_begin IS NULL) = (sustain_end IS NULL) AND (sustain_begin IS NULL) = (sustain_mode IS NULL)),
        CHECK (
            (vibrato_speed IS NULL) = (vibrato_depth IS NULL) AND
            (vibrato_speed IS NULL) = (vibrato_rate IS NULL) AND
            (vibrato_speed IS NULL) = (vibrato_waveform IS NULL)
        )
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sample_relation (
        id                  INTEGER PRIMARY KEY DEFAULT nextval('sample_relation_id_seq'),
        subject_hash        VARCHAR(64) NOT NULL REFERENCES sample(hash),
        reference_hash      VARCHAR(64) NOT NULL REFERENCES sample(hash),
        relation_type       VARCHAR NOT NULL CHECK (relation_type IN ('bit_depth_variant', 'resampled_variant')),
        method               VARCHAR NOT NULL,
        confidence           DOUBLE NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
        evidence             VARCHAR NOT NULL,
        detected_at          TIMESTAMPTZ NOT NULL,
        reviewed_confirmed   BOOLEAN,
        reviewed_at          TIMESTAMPTZ,
        reviewed_by          VARCHAR,
        CHECK (subject_hash < reference_hash),
        CHECK ((reviewed_confirmed IS NULL) = (reviewed_at IS NULL) AND (reviewed_at IS NULL) = (reviewed_by IS NULL)),
        UNIQUE (subject_hash, reference_hash, relation_type, method)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sample_cloud_coordinates (
        sample_hash  VARCHAR(64) PRIMARY KEY REFERENCES sample(hash),
        x            DOUBLE NOT NULL,
        y            DOUBLE NOT NULL,
        computed_at  TIMESTAMPTZ NOT NULL
    )
    """,
)


def connect(database_path: Path, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open the library's DuckDB catalog, creating its schema on first use.

    Schema creation is skipped for a read-only connection: a read-only process must never be the
    one to bring a catalog into existence, only ever attach to one another process has prepared.
    """
    connection = duckdb.connect(str(database_path), read_only=read_only)
    if not read_only:
        create_schema(connection)

    return connection


def create_schema(connection: duckdb.DuckDBPyConnection) -> None:
    """Create every table and sequence the catalog needs, where it does not already exist."""
    for statement in _SCHEMA_STATEMENTS:
        connection.execute(statement)
