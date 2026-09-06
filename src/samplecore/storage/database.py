from __future__ import annotations

from pathlib import Path
from typing import Final

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
from sqlalchemy.engine import URL, RootTransaction
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
# there is enforced here automatically rather than needing a second, easily-forgotten edit -- the
# schema can still never alter an already-existing table's constraint (see repair_schema.py), but
# this at least keeps a *new* table's constraint from drifting out of sync with its own enum.
_BIT_DEPTH_VALUES: Final[tuple[int, ...]] = tuple(depth.value for depth in BitDepth)
_CHANNEL_LAYOUT_VALUES: Final[tuple[int, ...]] = tuple(layout.value for layout in ChannelLayout)
_TRACKER_FORMAT_VALUES: Final[tuple[str, ...]] = tuple(tracker.value for tracker in TrackerFormat)
_LOOP_MODE_VALUES: Final[tuple[str, ...]] = tuple(mode.value for mode in LoopMode)
_RELATION_TYPE_VALUES: Final[tuple[str, ...]] = tuple(relation_type.value for relation_type in RelationType)


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
    CheckConstraint(column("volume") <= 64, name="sample_properties_volume_check"),
    CheckConstraint(column("panning") <= 255, name="sample_properties_panning_check"),
    CheckConstraint(column("loop_mode").in_(_LOOP_MODE_VALUES), name="sample_properties_loop_mode_check"),
    CheckConstraint(
        _all_null_together("loop_begin", "loop_end", "loop_mode"), name="sample_properties_loop_conull_check"
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
    CheckConstraint(column("global_volume") <= 64, name="it_sample_properties_global_volume_check"),
    CheckConstraint(column("sustain_mode").in_(_LOOP_MODE_VALUES), name="it_sample_properties_sustain_mode_check"),
    CheckConstraint(
        _all_null_together("sustain_begin", "sustain_end", "sustain_mode"),
        name="it_sample_properties_sustain_conull_check",
    ),
    CheckConstraint(
        _all_null_together("vibrato_speed", "vibrato_depth", "vibrato_rate", "vibrato_waveform"),
        name="it_sample_properties_vibrato_conull_check",
    ),
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
