from __future__ import annotations

from pathlib import Path

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Connection,
    DateTime,
    Double,
    Engine,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    Sequence,
    String,
    Table,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.engine import URL, RootTransaction
from sqlalchemy.pool import NullPool
from sqlalchemy.types import ARRAY

from samplecore.storage.types import TinyInt, UBigInt, UInteger, USmallInt, UTinyInt

metadata = MetaData()

module_id_sequence = Sequence("module_id_seq")
sample_relation_id_sequence = Sequence("sample_relation_id_seq")

sample = Table(
    "sample",
    metadata,
    Column("hash", String(64), primary_key=True),
    Column("depth", UTinyInt, nullable=False),
    Column("channels", UTinyInt, nullable=False),
    Column("frames", UInteger, nullable=False),
    CheckConstraint("depth IN (8, 16)", name="sample_depth_check"),
    CheckConstraint("channels IN (1, 2)", name="sample_channels_check"),
    CheckConstraint("frames > 0", name="sample_frames_check"),
)

module = Table(
    "module",
    metadata,
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
    CheckConstraint(r"filename NOT LIKE '%/%' AND filename NOT LIKE '%\%'", name="module_filename_check"),
    CheckConstraint("tracker IN ('xm', 'it')", name="module_tracker_check"),
)

sample_properties = Table(
    "sample_properties",
    metadata,
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
    CheckConstraint("rate > 0", name="sample_properties_rate_check"),
    CheckConstraint("volume <= 64", name="sample_properties_volume_check"),
    CheckConstraint("panning <= 255", name="sample_properties_panning_check"),
    CheckConstraint("loop_mode IN ('forward', 'ping_pong')", name="sample_properties_loop_mode_check"),
    CheckConstraint(
        "(loop_begin IS NULL) = (loop_end IS NULL) AND (loop_begin IS NULL) = (loop_mode IS NULL)",
        name="sample_properties_loop_conull_check",
    ),
)

xm_sample_properties = Table(
    "xm_sample_properties",
    metadata,
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

it_sample_properties = Table(
    "it_sample_properties",
    metadata,
    Column("module_id", Integer, nullable=False),
    Column("instrument_index", USmallInt, nullable=False),
    Column("sample_slot", USmallInt, nullable=False),
    Column("global_volume", UTinyInt, nullable=False),
    Column("sustain_begin", UInteger, nullable=True),
    Column("sustain_end", UInteger, nullable=True),
    Column("sustain_mode", String, nullable=True),
    Column("filename", String, nullable=True),
    Column("vibrato_speed", UTinyInt, nullable=True),
    Column("vibrato_depth", UTinyInt, nullable=True),
    Column("vibrato_rate", UTinyInt, nullable=True),
    Column("vibrato_waveform", UTinyInt, nullable=True),
    PrimaryKeyConstraint("module_id", "instrument_index", "sample_slot"),
    ForeignKeyConstraint(
        ["module_id", "instrument_index", "sample_slot"],
        ["sample_properties.module_id", "sample_properties.instrument_index", "sample_properties.sample_slot"],
    ),
    CheckConstraint("global_volume <= 64", name="it_sample_properties_global_volume_check"),
    CheckConstraint("sustain_mode IN ('forward', 'ping_pong')", name="it_sample_properties_sustain_mode_check"),
    CheckConstraint(
        "(sustain_begin IS NULL) = (sustain_end IS NULL) AND (sustain_begin IS NULL) = (sustain_mode IS NULL)",
        name="it_sample_properties_sustain_conull_check",
    ),
    CheckConstraint(
        """
        (vibrato_speed IS NULL) = (vibrato_depth IS NULL) AND
        (vibrato_speed IS NULL) = (vibrato_rate IS NULL) AND
        (vibrato_speed IS NULL) = (vibrato_waveform IS NULL)
        """,
        name="it_sample_properties_vibrato_conull_check",
    ),
)

sample_relation = Table(
    "sample_relation",
    metadata,
    Column(
        "id",
        Integer,
        sample_relation_id_sequence,
        primary_key=True,
        server_default=sample_relation_id_sequence.next_value(),
    ),
    Column("subject_hash", String(64), ForeignKey("sample.hash"), nullable=False),
    Column("reference_hash", String(64), ForeignKey("sample.hash"), nullable=False),
    Column("relation_type", String, nullable=False),
    Column("method", String, nullable=False),
    Column("confidence", Double, nullable=False),
    Column("evidence", String, nullable=False),
    Column("detected_at", DateTime(timezone=True), nullable=False),
    Column("reviewed_confirmed", Boolean, nullable=True),
    Column("reviewed_at", DateTime(timezone=True), nullable=True),
    Column("reviewed_by", String, nullable=True),
    CheckConstraint(
        "relation_type IN ('bit_depth_variant', 'resampled_variant', 'amplification_variant')",
        name="sample_relation_type_check",
    ),
    CheckConstraint("confidence BETWEEN 0.0 AND 1.0", name="sample_relation_confidence_check"),
    CheckConstraint("subject_hash < reference_hash", name="sample_relation_hash_order_check"),
    CheckConstraint(
        "(reviewed_confirmed IS NULL) = (reviewed_at IS NULL) AND (reviewed_at IS NULL) = (reviewed_by IS NULL)",
        name="sample_relation_review_conull_check",
    ),
    UniqueConstraint(
        "subject_hash", "reference_hash", "relation_type", "method", name="sample_relation_identity_unique"
    ),
)

sample_cloud_coordinates = Table(
    "sample_cloud_coordinates",
    metadata,
    Column("sample_hash", String(64), ForeignKey("sample.hash"), primary_key=True),
    Column("x", Double, nullable=False),
    Column("y", Double, nullable=False),
    Column("computed_at", DateTime(timezone=True), nullable=False),
)

sample_thumbnail = Table(
    "sample_thumbnail",
    metadata,
    Column("sample_hash", String(64), ForeignKey("sample.hash"), primary_key=True),
    Column("bucket_count", UTinyInt, nullable=False),
    Column("minimums", ARRAY(Double), nullable=False),
    Column("maximums", ARRAY(Double), nullable=False),
    CheckConstraint("bucket_count > 0", name="sample_thumbnail_bucket_count_check"),
)


def connect(database_path: Path, *, read_only: bool = False) -> Connection:
    """Open the library's DuckDB catalog, creating its schema on first use.

    Schema creation is skipped for a read-only connection: a read-only process must never be the
    one to bring a catalog into existence, only ever attach to one another process has prepared.
    ``NullPool`` gives every call its own dedicated DBAPI connection, closed for real (not merely
    returned to a pool) the moment the caller closes it -- the same one-connection-in, one-close-out
    lifecycle this catalog has always had.
    """
    url = URL.create(drivername="duckdb", database=str(database_path))
    engine = create_engine(url, connect_args={"read_only": read_only}, poolclass=NullPool)
    connection = engine.connect()
    if not read_only:
        create_schema(connection)
        connection.commit()

    return connection


def create_schema(bind: Connection | Engine) -> None:
    """Create every table and sequence the catalog needs, where it does not already exist."""
    metadata.create_all(bind)


def start_batch(connection: Connection) -> RootTransaction:
    """Begin a fresh transaction for a multi-statement batch, regardless of what came before.

    SQLAlchemy autobegins an implicit transaction on a connection's first statement -- including a
    plain read -- and refuses a second ``begin()`` until that one is closed. Closing whatever the
    connection's own prior reads or writes left open first is what lets a batch like
    ``ingest_module`` or ``detect_equivalences`` always open its own transaction cleanly, no matter
    what the connection was used for immediately before.
    """
    connection.commit()
    return connection.begin()
