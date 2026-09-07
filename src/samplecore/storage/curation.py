from __future__ import annotations

from typing import Final

from sqlalchemy import CheckConstraint, Column, Connection, DateTime, Engine, MetaData, String, Table, column, event
from sqlalchemy.schema import CreateSchema

from samplecore.models.label import LabelSource
from samplecore.storage.constraints import non_negative
from samplecore.storage.types import USmallInt

CURATION_SCHEMA: Final[str] = "curation"

_LABEL_SOURCE_VALUES: Final[tuple[str, ...]] = tuple(source.value for source in LabelSource)

# A MetaData of its own, in a schema of its own, is what keeps hand-made work safe from the passes
# that rebuild everything else. Both places this project empties a database -- `scripts/reset_library.py`
# and the test suite's own teardown -- iterate `database.metadata.sorted_tables`, so a table registered
# here is beyond their reach by construction rather than by an exemption list somebody has to maintain.
# For the same reason nothing here carries a foreign key into the catalog: one would either delete
# these rows along with the samples or block the purge outright.
curation_metadata = MetaData(schema=CURATION_SCHEMA)

sample_label = Table(
    "sample_label",
    curation_metadata,
    Column("sample_hash", String(64), primary_key=True),
    Column("label", String, nullable=False),
    Column("module_hash", String(64), nullable=False),
    Column("module_filename", String, nullable=False),
    Column("instrument_index", USmallInt, nullable=False),
    Column("sample_slot", USmallInt, nullable=False),
    Column("sample_name", String, nullable=False),
    Column("source", String, nullable=False),
    Column("labeled_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(column("label") != "", name="sample_label_label_check"),
    CheckConstraint(column("source").in_(_LABEL_SOURCE_VALUES), name="sample_label_source_check"),
    CheckConstraint(non_negative("instrument_index"), name="sample_label_instrument_index_check"),
    CheckConstraint(non_negative("sample_slot"), name="sample_label_sample_slot_check"),
)

# SQLAlchemy creates tables but never the schema qualifying them, so the CREATE SCHEMA is attached
# as the event that runs first on this metadata's own create_all.
event.listen(curation_metadata, "before_create", CreateSchema(CURATION_SCHEMA, if_not_exists=True))


def create_curation_schema(bind: Connection | Engine) -> None:
    """Create the curation schema and its tables, where they do not already exist."""
    curation_metadata.create_all(bind)
