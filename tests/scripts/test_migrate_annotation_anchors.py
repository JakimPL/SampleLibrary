from __future__ import annotations

import importlib.util
import types
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from samplecore.models.annotation import ModuleSlotAnchor
from samplecore.storage.curation import CURATION_SCHEMA, MODULE_SLOT_ANCHOR_COLUMNS, SAMPLE_FILE_ANCHOR_COLUMNS
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "migrate_annotation_anchors.py"
TABLE = f"{CURATION_SCHEMA}.sample_annotation"
SAMPLE_HASH = "a" * 64


def _load_script() -> types.ModuleType:
    """Imports the script by file path -- it lives outside every installed package, by design."""
    spec = importlib.util.spec_from_file_location("migrate_annotation_anchors", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migrate_annotation_anchors = _load_script()


@pytest.fixture
def table_in_its_earlier_shape(connection: Connection) -> None:
    """The annotation table as a library written before sample files holds it, with one annotation on file."""
    for name in migrate_annotation_anchors.ANCHOR_CONSTRAINT_NAMES:
        connection.execute(text(f"ALTER TABLE {TABLE} DROP CONSTRAINT {name}"))
    for name in SAMPLE_FILE_ANCHOR_COLUMNS:
        connection.execute(text(f"ALTER TABLE {TABLE} DROP COLUMN {name}"))
    for name in MODULE_SLOT_ANCHOR_COLUMNS:
        connection.execute(text(f"ALTER TABLE {TABLE} ALTER COLUMN {name} SET NOT NULL"))
    connection.execute(
        text(
            f"INSERT INTO {TABLE} (sample_hash, label, rating, favorite, module_hash, module_filename, "
            "instrument_index, sample_slot, sample_name, source, annotated_at) "
            "VALUES (:sample_hash, 'KICK', 4, true, :module_hash, 'song.xm', 0, 1, 'kick', 'sample', :annotated_at)"
        ),
        {"sample_hash": SAMPLE_HASH, "module_hash": "c" * 64, "annotated_at": datetime.now(UTC)},
    )
    connection.commit()


def test_an_annotation_written_before_sample_files_keeps_its_decisions_and_its_module_slot(
    connection: Connection, table_in_its_earlier_shape: None
) -> None:
    migrate_annotation_anchors.migrate_annotation_anchors(connection)
    migrate_annotation_anchors.migrate_annotation_anchors(connection)

    stored = PostgresSampleAnnotationRepository(connection).get(SAMPLE_HASH)

    assert stored is not None
    assert (stored.label, stored.rating, stored.favorite) == ("KICK", 4, True)
    assert isinstance(stored.anchor, ModuleSlotAnchor)
    assert (stored.anchor.module_filename, stored.anchor.occurrence.sample_slot) == ("song.xm", 1)


def test_the_migrated_table_holds_every_row_to_one_anchor(
    connection: Connection, table_in_its_earlier_shape: None
) -> None:
    migrate_annotation_anchors.migrate_annotation_anchors(connection)

    with pytest.raises(IntegrityError):
        connection.execute(text(f"UPDATE {TABLE} SET file_directory = '/samples', file_relative_path = 'kick.wav'"))
    connection.rollback()
