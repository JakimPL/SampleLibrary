from __future__ import annotations

from collections.abc import Iterable
from typing import Final, cast

from psycopg import Connection as PsycopgConnection
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ColumnElement,
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
    and_,
    column,
    create_engine,
)
from sqlalchemy.engine import RootTransaction
from sqlalchemy.pool import NullPool
from sqlalchemy.types import ARRAY
from trackmod.core.samples.depth import BitDepth
from trackmod.core.samples.loop import LoopMode

from samplecore.models.channels import ChannelLayout
from samplecore.models.relation import RelationType
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.types import TinyInt, UBigInt, UInteger, USmallInt, UTinyInt

# Each CHECK constraint below that enumerates a closed set of values is derived from the same enum
# the rest of the codebase already treats as that set's single source of truth, so a member added
# there is enforced here automatically rather than needing a second, easily-forgotten edit. Postgres
# supports `ALTER TABLE ... {ADD,DROP} CONSTRAINT` natively, so an already-existing table's own
# constraint can still be brought up to date directly, unlike this metadata definition alone.
_BIT_DEPTH_VALUES: Final[tuple[int, ...]] = tuple(depth.value for depth in BitDepth)
_CHANNEL_LAYOUT_VALUES: Final[tuple[int, ...]] = tuple(layout.value for layout in ChannelLayout)
_TRACKER_FORMAT_VALUES: Final[tuple[str, ...]] = tuple(tracker.value for tracker in TrackerFormat)
_LOOP_MODE_VALUES: Final[tuple[str, ...]] = tuple(mode.value for mode in LoopMode)
_RELATION_TYPE_VALUES: Final[tuple[str, ...]] = tuple(relation_type.value for relation_type in RelationType)


def _non_negative(column_name: str) -> ColumnElement[bool]:
    """A CHECK expression requiring a column to never go negative.

    DuckDB's own unsigned integer types (``UTINYINT``, ``USMALLINT``, ``UINTEGER``, ``UBIGINT``)
    enforced this at the type level for free; Postgres has no unsigned integer type at all, so every
    column that relied on that now needs it spelled out here instead.
    """
    return column(column_name) >= 0


def _all_null_together(first_column_name: str, *other_column_names: str) -> ColumnElement[bool]:
    """A CHECK expression requiring a group of columns to be either all NULL or all filled in.

    Every other column's nullability is compared against the first's; boolean equality is
    transitive, so this enforces the same all-or-none constraint as comparing each consecutive
    pair, without needing that specific chain to read the intent off the expression.
    """
    first_is_null = column(first_column_name).is_(None)
    return and_(*(first_is_null == column(name).is_(None) for name in other_column_names))


metadata = MetaData()

module_id_sequence = Sequence("module_id_seq")
sample_relation_id_sequence = Sequence("sample_relation_id_seq")
experiment_id_sequence = Sequence("experiment_id_seq")

sample = Table(
    "sample",
    metadata,
    Column("hash", String(64), primary_key=True),
    Column("depth", UTinyInt, nullable=False),
    Column("channels", UTinyInt, nullable=False),
    Column("frames", UInteger, nullable=False),
    CheckConstraint(column("depth").in_(_BIT_DEPTH_VALUES), name="sample_depth_check"),
    CheckConstraint(column("channels").in_(_CHANNEL_LAYOUT_VALUES), name="sample_channels_check"),
    CheckConstraint(column("frames") > 0, name="sample_frames_check"),
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
    CheckConstraint(
        column("filename").not_like("%/%") & column("filename").not_like(r"%\%"), name="module_filename_check"
    ),
    CheckConstraint(column("tracker").in_(_TRACKER_FORMAT_VALUES), name="module_tracker_check"),
    CheckConstraint(_non_negative("channel_count"), name="module_channel_count_check"),
    CheckConstraint(_non_negative("pattern_count"), name="module_pattern_count_check"),
    CheckConstraint(_non_negative("instrument_count"), name="module_instrument_count_check"),
    CheckConstraint(_non_negative("sample_count"), name="module_sample_count_check"),
    CheckConstraint(_non_negative("file_size"), name="module_file_size_check"),
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
    CheckConstraint(column("tracker").in_(_TRACKER_FORMAT_VALUES), name="sample_properties_tracker_check"),
    CheckConstraint(column("rate") > 0, name="sample_properties_rate_check"),
    CheckConstraint(column("volume").between(0, 64), name="sample_properties_volume_check"),
    CheckConstraint(column("panning").between(0, 255), name="sample_properties_panning_check"),
    CheckConstraint(column("loop_mode").in_(_LOOP_MODE_VALUES), name="sample_properties_loop_mode_check"),
    CheckConstraint(
        _all_null_together("loop_begin", "loop_end", "loop_mode"), name="sample_properties_loop_conull_check"
    ),
    CheckConstraint(_non_negative("instrument_index"), name="sample_properties_instrument_index_check"),
    CheckConstraint(_non_negative("sample_slot"), name="sample_properties_sample_slot_check"),
    CheckConstraint(_non_negative("loop_begin"), name="sample_properties_loop_begin_check"),
    CheckConstraint(_non_negative("loop_end"), name="sample_properties_loop_end_check"),
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
    CheckConstraint(column("global_volume").between(0, 64), name="it_sample_properties_global_volume_check"),
    CheckConstraint(column("sustain_mode").in_(_LOOP_MODE_VALUES), name="it_sample_properties_sustain_mode_check"),
    CheckConstraint(
        _all_null_together("sustain_begin", "sustain_end", "sustain_mode"),
        name="it_sample_properties_sustain_conull_check",
    ),
    CheckConstraint(
        _all_null_together("vibrato_speed", "vibrato_depth", "vibrato_rate", "vibrato_waveform"),
        name="it_sample_properties_vibrato_conull_check",
    ),
    CheckConstraint(_non_negative("sustain_begin"), name="it_sample_properties_sustain_begin_check"),
    CheckConstraint(_non_negative("sustain_end"), name="it_sample_properties_sustain_end_check"),
    CheckConstraint(_non_negative("vibrato_speed"), name="it_sample_properties_vibrato_speed_check"),
    CheckConstraint(_non_negative("vibrato_depth"), name="it_sample_properties_vibrato_depth_check"),
    CheckConstraint(_non_negative("vibrato_rate"), name="it_sample_properties_vibrato_rate_check"),
    CheckConstraint(_non_negative("vibrato_waveform"), name="it_sample_properties_vibrato_waveform_check"),
)

s3m_sample_properties = Table(
    "s3m_sample_properties",
    metadata,
    Column("module_id", Integer, nullable=False),
    Column("instrument_index", USmallInt, nullable=False),
    Column("sample_slot", USmallInt, nullable=False),
    Column("filename", String, nullable=True),
    PrimaryKeyConstraint("module_id", "instrument_index", "sample_slot"),
    ForeignKeyConstraint(
        ["module_id", "instrument_index", "sample_slot"],
        ["sample_properties.module_id", "sample_properties.instrument_index", "sample_properties.sample_slot"],
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
    CheckConstraint(column("relation_type").in_(_RELATION_TYPE_VALUES), name="sample_relation_type_check"),
    CheckConstraint(column("confidence").between(0.0, 1.0), name="sample_relation_confidence_check"),
    CheckConstraint(column("subject_hash") < column("reference_hash"), name="sample_relation_hash_order_check"),
    CheckConstraint(
        _all_null_together("reviewed_confirmed", "reviewed_at", "reviewed_by"),
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

module_cloud_coordinates = Table(
    "module_cloud_coordinates",
    metadata,
    Column("module_hash", String(64), ForeignKey("module.hash"), primary_key=True),
    Column("x", Double, nullable=False),
    Column("y", Double, nullable=False),
    Column("computed_at", DateTime(timezone=True), nullable=False),
)

sample_spectral_feature = Table(
    "sample_spectral_feature",
    metadata,
    Column("sample_hash", String(64), ForeignKey("sample.hash"), primary_key=True),
    Column("vector", String, nullable=False),
    Column("computed_at", DateTime(timezone=True), nullable=False),
)

sample_thumbnail = Table(
    "sample_thumbnail",
    metadata,
    Column("sample_hash", String(64), ForeignKey("sample.hash"), primary_key=True),
    Column("bucket_count", UTinyInt, nullable=False),
    Column("minimums", ARRAY(Double), nullable=False),
    Column("maximums", ARRAY(Double), nullable=False),
    CheckConstraint(column("bucket_count") > 0, name="sample_thumbnail_bucket_count_check"),
)

experiment = Table(
    "experiment",
    metadata,
    Column("id", Integer, experiment_id_sequence, primary_key=True, server_default=experiment_id_sequence.next_value()),
    Column("backend_name", String, nullable=False),
    Column("params", String, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("label", String, nullable=True),
)

sample_feature_vector = Table(
    "sample_feature_vector",
    metadata,
    Column("experiment_id", Integer, ForeignKey("experiment.id"), nullable=False),
    Column("sample_hash", String(64), ForeignKey("sample.hash"), nullable=False),
    Column("vector", ARRAY(Double), nullable=False),
    Column("computed_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("experiment_id", "sample_hash"),
)


def connect(database_url: str, *, read_only: bool = False) -> Connection:
    """Open the library's Postgres catalog, creating its schema on first use.

    Schema creation is skipped for a read-only connection: a read-only process must never be the
    one to bring a catalog into existence, only ever attach to one another process has prepared.
    Read-only is enforced at the transaction level (``postgresql_readonly``), rejected server-side
    for any write the same as a role-level grant would, without needing a second role provisioned.
    ``NullPool`` gives every call its own dedicated DBAPI connection, closed for real (not merely
    returned to a pool) the moment the caller closes it -- the same one-connection-in, one-close-out
    lifecycle this catalog has always had.
    """
    engine = create_engine(database_url, poolclass=NullPool)
    connection = engine.connect()
    if read_only:
        connection = connection.execution_options(postgresql_readonly=True)
    else:
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


def bulk_insert(
    connection: Connection, table: Table, column_names: Iterable[str], rows: Iterable[Iterable[object]]
) -> None:
    """Insert many rows into ``table`` by way of Postgres's own ``COPY ... FROM STDIN``.

    A database's own bulk-format loader is dramatically faster than parameterized per-row inserts at
    this catalog's scale -- ``executemany`` and one large multi-row ``VALUES`` statement were both
    measured, under this project's previous engine, at the same few-milliseconds-per-row cost
    regardless of batch size, turning tens of thousands of rows into minutes rather than a fraction
    of a second. ``psycopg``'s own ``Copy.write_row`` streams each row over the connection already
    open for everything else, adapting every value to Postgres's wire format itself -- no
    client-side CSV encoding, and no shared-filesystem assumption between client and server, unlike
    a file-path-based ``COPY``. SQLAlchemy's ``Connection`` has no ``COPY`` construct of its own, so
    reaching for the underlying ``psycopg`` connection directly is this function's whole purpose,
    not a workaround of one.

    A constraint violation here raises a ``psycopg.Error`` subtype directly, not the
    ``sqlalchemy.exc`` equivalent a normal ``connection.execute(...)`` call would -- this path never
    goes through SQLAlchemy's own statement execution, so its exception-wrapping never applies.
    """
    quoted_columns = ", ".join(f'"{column_name}"' for column_name in column_names)
    psycopg_connection = cast(PsycopgConnection, connection.connection.dbapi_connection)
    with psycopg_connection.cursor() as cursor:
        with cursor.copy(f'COPY "{table.name}" ({quoted_columns}) FROM STDIN') as copy:
            for row in rows:
                copy.write_row(tuple(row))
