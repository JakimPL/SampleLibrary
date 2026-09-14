from __future__ import annotations

from typing import Final

from sqlalchemy import CheckConstraint, Connection, inspect, text
from sqlalchemy.schema import AddConstraint, DropConstraint

from samplecore.cli_support import load_config_or_exit
from samplecore.storage.curation import (
    CURATION_SCHEMA,
    MODULE_SLOT_ANCHOR_COLUMNS,
    SAMPLE_FILE_ANCHOR_COLUMNS,
    claim_annotation_writes,
    sample_annotation,
)
from samplecore.storage.database import connect_for_curation, start_batch

ANCHOR_CONSTRAINT_NAMES: Final[frozenset[str]] = frozenset(
    {"sample_annotation_module_slot_check", "sample_annotation_sample_file_check", "sample_annotation_anchor_check"}
)


def migrate_annotation_anchors(connection: Connection) -> None:
    """Bring a library's hand annotations to the table shape that anchors a sample to a module slot or a file.

    Every row already on file is anchored to a module slot and keeps its values: the module slot
    columns take empty values from now on, the sample file columns are added beside them, and the
    checks holding each row to exactly one anchor are put in place. Each step reads what the table
    already has, so running it again changes nothing, and the whole of it is one transaction under
    the annotation write lock.
    """
    table_name = f"{CURATION_SCHEMA}.{sample_annotation.name}"
    with start_batch(connection):
        claim_annotation_writes(connection)
        existing = {
            column["name"] for column in inspect(connection).get_columns(sample_annotation.name, schema=CURATION_SCHEMA)
        }
        for name in SAMPLE_FILE_ANCHOR_COLUMNS:
            if name not in existing:
                column_type = sample_annotation.c[name].type.compile(dialect=connection.dialect)
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {name} {column_type}"))
        for name in MODULE_SLOT_ANCHOR_COLUMNS:
            connection.execute(text(f"ALTER TABLE {table_name} ALTER COLUMN {name} DROP NOT NULL"))
        for constraint in _anchor_constraints():
            connection.execute(DropConstraint(constraint, if_exists=True))
            connection.execute(AddConstraint(constraint))


def _anchor_constraints() -> tuple[CheckConstraint, ...]:
    return tuple(
        constraint
        for constraint in sample_annotation.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name in ANCHOR_CONSTRAINT_NAMES
    )


def main() -> None:
    """Migrate the annotations of the library ``SAMPLELIBRARY_CONFIG`` or ``config.toml`` names."""
    config = load_config_or_exit()
    connection = connect_for_curation(config.database_url)
    try:
        migrate_annotation_anchors(connection)
    finally:
        connection.close()
    print("Hand annotations now anchor a sample to a module slot or to a sample file.")


if __name__ == "__main__":
    main()
