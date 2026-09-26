from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Connection,
    DateTime,
    Identity,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    column,
    event,
    func,
    insert,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import CreateSchema

from samplecore.labeling.labels import LEVEL_SEPARATOR, LabelPath, first_use_ranks, format_path
from samplecore.models.annotation import AnnotationSource, HistoryOperation
from samplecore.models.scalars import MAXIMUM_RATING, MINIMUM_RATING
from samplecore.storage.constraints import all_null_together, non_negative
from samplecore.storage.types import USmallInt, UTinyInt

CURATION_SCHEMA: Final[str] = "curation"
# An arbitrary number, needing only to be one no other advisory lock in this database picks.
ANNOTATION_WRITE_LOCK_KEY: Final[int] = 4_120_559_871_306_442_117

_ANNOTATION_SOURCE_VALUES: Final[tuple[str, ...]] = tuple(source.value for source in AnnotationSource)
_HISTORY_OPERATION_VALUES: Final[tuple[str, ...]] = tuple(operation.value for operation in HistoryOperation)
_OPERATIONS_WITHOUT_PREVIOUS_ROW: Final[tuple[str, ...]] = (
    HistoryOperation.BASELINE.value,
    HistoryOperation.INSERT.value,
)
ANNOTATION_HISTORY_TABLE: Final[str] = "annotation_history"
ANNOTATION_HISTORY_START_TABLE: Final[str] = "annotation_history_start"
MODULE_SLOT_ANCHOR_COLUMNS: Final[tuple[str, ...]] = (
    "module_hash",
    "module_filename",
    "instrument_index",
    "sample_slot",
    "sample_name",
)
SAMPLE_FILE_ANCHOR_COLUMNS: Final[tuple[str, ...]] = ("file_directory", "file_relative_path")

# A MetaData of its own, in a schema of its own, is what keeps hand-made work safe from the passes
# that rebuild everything else. Both places this project empties a database -- `samplelibrary reset`
# and the test suite's own teardown -- iterate `database.metadata.sorted_tables`, so a table registered
# here is beyond their reach by construction rather than by an exemption list somebody has to maintain.
# For the same reason nothing here carries a foreign key into the catalog: one would either delete
# these rows along with the samples or block the purge outright.
curation_metadata = MetaData(schema=CURATION_SCHEMA)

sample_annotation = Table(
    "sample_annotation",
    curation_metadata,
    Column("sample_hash", String(64), primary_key=True),
    Column("label", String, nullable=True),
    Column("rating", UTinyInt, nullable=True),
    Column("favorite", Boolean, nullable=False),
    Column("module_hash", String(64), nullable=True),
    Column("module_filename", String, nullable=True),
    Column("instrument_index", USmallInt, nullable=True),
    Column("sample_slot", USmallInt, nullable=True),
    Column("sample_name", String, nullable=True),
    Column("file_directory", String, nullable=True),
    Column("file_relative_path", String, nullable=True),
    Column("source", String, nullable=False),
    Column("annotated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(column("label").is_(None) | (column("label") != ""), name="sample_annotation_label_check"),
    CheckConstraint(column("rating").between(MINIMUM_RATING, MAXIMUM_RATING), name="sample_annotation_rating_check"),
    # A row earns its place by recording a decision. This holds only because `favorite` is NOT NULL:
    # a CHECK rejects FALSE alone, so a nullable column here would let an empty row through as
    # UNKNOWN. `between` above is null-safe for the same reason it needs no separate guard.
    CheckConstraint(
        column("label").is_not(None) | column("rating").is_not(None) | column("favorite").is_(True),
        name="sample_annotation_decision_check",
    ),
    CheckConstraint(column("source").in_(_ANNOTATION_SOURCE_VALUES), name="sample_annotation_source_check"),
    # Every annotation is anchored exactly once: the module slot columns filled together, or the
    # sample file columns, and which of the two a row holds is what tells the anchor's kind.
    CheckConstraint(all_null_together(*MODULE_SLOT_ANCHOR_COLUMNS), name="sample_annotation_module_slot_check"),
    CheckConstraint(all_null_together(*SAMPLE_FILE_ANCHOR_COLUMNS), name="sample_annotation_sample_file_check"),
    CheckConstraint(
        column(MODULE_SLOT_ANCHOR_COLUMNS[0]).is_(None) != column(SAMPLE_FILE_ANCHOR_COLUMNS[0]).is_(None),
        name="sample_annotation_anchor_check",
    ),
    CheckConstraint(non_negative("instrument_index"), name="sample_annotation_instrument_index_check"),
    CheckConstraint(non_negative("sample_slot"), name="sample_annotation_sample_slot_check"),
)

tag_rank = Table(
    "tag_rank",
    curation_metadata,
    Column("path", String, primary_key=True),
    Column("rank", Integer, nullable=False, unique=True),
    CheckConstraint(non_negative("rank"), name="tag_rank_rank_check"),
)

# One row per labels file read into the table, named by the digest of its bytes, so a pipeline can
# tell a file the library already took in from one it has not.
annotation_import = Table(
    "annotation_import",
    curation_metadata,
    Column("file_sha256", String(64), primary_key=True),
    Column("annotation_count", Integer, nullable=False),
    Column("imported_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(non_negative("annotation_count"), name="annotation_import_annotation_count_check"),
)

# Every change to an annotation, written by the trigger `_begin_annotation_history` installs rather
# than by any writer, so a write through whatever connection lands here, and the one serving label
# edits holds no privilege on this table at all. `previous` and `current` are the whole row before
# and after, which is what a restore writes back.
annotation_history = Table(
    ANNOTATION_HISTORY_TABLE,
    curation_metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("sample_hash", String(64), nullable=False),
    Column("operation", String, nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False, server_default=func.transaction_timestamp()),
    Column("role", String, nullable=False, server_default=text("session_user")),
    Column("previous", JSONB, nullable=True),
    Column("current", JSONB, nullable=True),
    CheckConstraint(column("operation").in_(_HISTORY_OPERATION_VALUES), name="annotation_history_operation_check"),
    CheckConstraint(
        column("operation").in_(_OPERATIONS_WITHOUT_PREVIOUS_ROW) == column("previous").is_(None),
        name="annotation_history_previous_check",
    ),
    CheckConstraint(
        (column("operation") == HistoryOperation.DELETE.value) == column("current").is_(None),
        name="annotation_history_current_check",
    ),
    Index("annotation_history_sample_hash_id_index", "sample_hash", "id"),
    Index("annotation_history_recorded_at_index", "recorded_at"),
)

# The moment the history began, one row, since a history beginning over a library with no labels
# yet holds no entry from that moment until the first label, while every moment since it can be
# restored to.
annotation_history_start = Table(
    ANNOTATION_HISTORY_START_TABLE,
    curation_metadata,
    Column("began_at", DateTime(timezone=True), primary_key=True, server_default=func.transaction_timestamp()),
)

# The trigger function runs with its owner's rights, which are the ones that write the history,
# and a pinned search path, so no role invoking it can reach anything else through it.
_RECORDING_FUNCTION: Final[str] = f"""
CREATE FUNCTION {CURATION_SCHEMA}.record_annotation_change() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD IS NOT DISTINCT FROM NEW THEN
        RETURN NULL;
    END IF;
    INSERT INTO {CURATION_SCHEMA}.{ANNOTATION_HISTORY_TABLE} (sample_hash, operation, previous, current)
    VALUES (
        CASE WHEN TG_OP = 'DELETE' THEN OLD.sample_hash ELSE NEW.sample_hash END,
        lower(TG_OP),
        CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) END,
        CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) END
    );
    RETURN NULL;
END
$$
"""
_RECORDING_FUNCTION_PRIVILEGES: Final[str] = (
    f"REVOKE ALL ON FUNCTION {CURATION_SCHEMA}.record_annotation_change() FROM PUBLIC"
)
_RECORDING_TRIGGER: Final[str] = (
    f"CREATE TRIGGER sample_annotation_history AFTER INSERT OR UPDATE OR DELETE "
    f"ON {CURATION_SCHEMA}.sample_annotation FOR EACH ROW "
    f"EXECUTE FUNCTION {CURATION_SCHEMA}.record_annotation_change()"
)
_HISTORY_START: Final[tuple[str, ...]] = (
    f"DELETE FROM {CURATION_SCHEMA}.{ANNOTATION_HISTORY_START_TABLE}",
    f"INSERT INTO {CURATION_SCHEMA}.{ANNOTATION_HISTORY_START_TABLE} DEFAULT VALUES",
)
_BASELINE: Final[str] = (
    f"INSERT INTO {CURATION_SCHEMA}.{ANNOTATION_HISTORY_TABLE} (sample_hash, operation, current) "
    f"SELECT sample_hash, '{HistoryOperation.BASELINE.value}', to_jsonb(annotation) "
    f"FROM {CURATION_SCHEMA}.sample_annotation AS annotation"
)

# SQLAlchemy creates tables but never the schema qualifying them, so the CREATE SCHEMA is attached
# as the event that runs first on this metadata's own create_all.
event.listen(curation_metadata, "before_create", CreateSchema(CURATION_SCHEMA, if_not_exists=True))


def create_curation_schema(connection: Connection) -> None:
    """Create the curation schema and its tables where they are missing, and rank the tags already in use.

    A library whose labels predate the rank table gets ranks in the order its tags were first used,
    which is the order it was colored in until then. The label history begins the moment its table
    is created, with every annotation standing then.
    """
    history_begins = not connection.dialect.has_table(connection, ANNOTATION_HISTORY_TABLE, schema=CURATION_SCHEMA)
    curation_metadata.create_all(connection)
    if history_begins:
        _begin_annotation_history(connection)
    claim_annotation_writes(connection)
    if not read_tag_ranks(connection):
        labels = connection.execute(
            select(sample_annotation.c.label)
            .where(sample_annotation.c.label.is_not(None))
            .order_by(sample_annotation.c.annotated_at, sample_annotation.c.sample_hash)
        ).scalars()
        register_tag_ranks(connection, labels)


def _begin_annotation_history(connection: Connection) -> None:
    """Install the trigger recording every change to an annotation, and record the moment and the annotations standing now.

    The table's creation and this run in one transaction under the schema lock, and creating the
    trigger waits for writes in flight to end, so every annotation is either in the baseline or
    recorded by the trigger, never missed between the two.
    """
    for statement in (
        _RECORDING_FUNCTION,
        _RECORDING_FUNCTION_PRIVILEGES,
        _RECORDING_TRIGGER,
        *_HISTORY_START,
        _BASELINE,
    ):
        connection.execute(text(statement))


def claim_annotation_writes(connection: Connection) -> None:
    """Hold the annotation write lock until the caller's transaction ends.

    Every write to hand annotations reads what a sample holds, merges a change into it and writes
    the result back, so two writes landing on one sample together would each merge into a state the
    other is replacing. Taking one lock first puts them one after the other, and the second reads
    what the first committed. Writes arrive at the pace of a person's clicks, so waiting in turn
    costs nothing anyone notices.
    """
    connection.execute(select(func.pg_advisory_xact_lock(ANNOTATION_WRITE_LOCK_KEY)))


def read_tag_ranks(connection: Connection) -> dict[LabelPath, int]:
    """Every tag that has ever carried a rank, with that rank."""
    rows = connection.execute(select(tag_rank.c.path, tag_rank.c.rank)).fetchall()
    return {_path_of(row.path): int(row.rank) for row in rows}


def register_tag_ranks(connection: Connection, labels_in_time_order: Iterable[str]) -> None:
    """Give each tag these labels use for the first time the rank after the last one given.

    A rank stays with its tag once given, through a tag falling out of use and coming back, which is
    what lets a viewer keep one color per tag for as long as the library lives. Callers hold
    ``claim_annotation_writes``, so ranks are handed out one write at a time.
    """
    known = read_tag_ranks(connection)
    next_rank = max(known.values(), default=-1) + 1
    new_rows: list[dict[str, str | int]] = []
    for path in first_use_ranks(labels_in_time_order):
        if path not in known:
            known[path] = next_rank
            new_rows.append({"path": format_path(path), "rank": next_rank})
            next_rank += 1
    if new_rows:
        connection.execute(insert(tag_rank), new_rows)


def _path_of(stored_path: str) -> LabelPath:
    return tuple(level.strip() for level in stored_path.split(LEVEL_SEPARATOR))
