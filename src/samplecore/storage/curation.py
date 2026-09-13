from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Connection,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    column,
    event,
    func,
    insert,
    select,
)
from sqlalchemy.schema import CreateSchema

from samplecore.labeling.labels import LEVEL_SEPARATOR, LabelPath, first_use_ranks, format_path
from samplecore.models.annotation import AnnotationSource
from samplecore.models.scalars import MAXIMUM_RATING, MINIMUM_RATING
from samplecore.storage.constraints import non_negative
from samplecore.storage.types import USmallInt, UTinyInt

CURATION_SCHEMA: Final[str] = "curation"
# An arbitrary number, needing only to be one no other advisory lock in this database picks.
ANNOTATION_WRITE_LOCK_KEY: Final[int] = 4_120_559_871_306_442_117

_ANNOTATION_SOURCE_VALUES: Final[tuple[str, ...]] = tuple(source.value for source in AnnotationSource)

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
    Column("module_hash", String(64), nullable=False),
    Column("module_filename", String, nullable=False),
    Column("instrument_index", USmallInt, nullable=False),
    Column("sample_slot", USmallInt, nullable=False),
    Column("sample_name", String, nullable=False),
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

# SQLAlchemy creates tables but never the schema qualifying them, so the CREATE SCHEMA is attached
# as the event that runs first on this metadata's own create_all.
event.listen(curation_metadata, "before_create", CreateSchema(CURATION_SCHEMA, if_not_exists=True))


def create_curation_schema(connection: Connection) -> None:
    """Create the curation schema and its tables where they are missing, and rank the tags already in use.

    A library whose labels predate the rank table gets ranks in the order its tags were first used,
    which is the order it was colored in until then.
    """
    curation_metadata.create_all(connection)
    claim_annotation_writes(connection)
    if not read_tag_ranks(connection):
        labels = connection.execute(
            select(sample_annotation.c.label)
            .where(sample_annotation.c.label.is_not(None))
            .order_by(sample_annotation.c.annotated_at, sample_annotation.c.sample_hash)
        ).scalars()
        register_tag_ranks(connection, labels)


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
