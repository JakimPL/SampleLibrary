from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Connection, func, select

from samplecore.models.annotation import AnnotationSource, ModuleSlotAnchor, SampleAnnotation
from samplecore.models.module import Module
from samplecore.models.sample_properties import SampleOccurrence
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.database import connect, metadata
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository
from samplecore.storage.reset import RETIRED_SUFFIX, ResetRefused, reset_library


def _row_counts(connection: Connection) -> dict[str, int]:
    return {
        table.name: connection.execute(select(func.count()).select_from(table)).scalar_one()
        for table in metadata.sorted_tables
    }


def test_reset_library_empties_every_table_and_the_content_store(
    connection: Connection, populated_library: Path
) -> None:
    library_root = populated_library
    before = _row_counts(connection)
    assert all(count > 0 for count in before.values()), f"fixture left an empty table: {before}"
    objects_directory = library_root / "objects"
    assert any(objects_directory.rglob("*.wav"))

    reset_library(connection, library_root)
    connection.commit()

    after = _row_counts(connection)
    assert all(count == 0 for count in after.values()), f"reset left rows behind: {after}"
    assert objects_directory.is_dir()
    assert list(objects_directory.iterdir()) == []


def test_reset_library_leaves_hand_labels_untouched(connection: Connection, populated_library: Path) -> None:
    """Hand labels are the one thing in this library nobody can regenerate, so a purge leaves them.

    They live on a metadata of their own, which is what puts them beyond the reach of the loop over
    ``metadata.sorted_tables`` that empties everything else.
    """
    library_root = populated_library
    module = PostgresModuleRepository(connection).list_all()[0]
    occurrence_row = connection.execute(
        select(metadata.tables["sample_properties"]).where(
            metadata.tables["sample_properties"].c.module_id == module.id
        )
    ).fetchone()
    assert occurrence_row is not None

    annotation_repository = PostgresSampleAnnotationRepository(connection)
    annotation_repository.upsert_many(
        (
            SampleAnnotation(
                sample_hash=occurrence_row.sample_hash,
                label="warm pad",
                rating=None,
                favorite=False,
                anchor=ModuleSlotAnchor(
                    occurrence=SampleOccurrence(
                        module_hash=module.hash,
                        instrument_index=occurrence_row.instrument_index,
                        sample_slot=occurrence_row.sample_slot,
                    ),
                    module_filename=module.filename,
                    sample_name=occurrence_row.name,
                ),
                source=AnnotationSource.SAMPLE,
                annotated_at=datetime.now(UTC),
            ),
        )
    )
    connection.commit()

    reset_library(connection, library_root)
    connection.commit()

    assert all(count == 0 for count in _row_counts(connection).values())
    surviving = annotation_repository.get(occurrence_row.sample_hash)
    assert surviving is not None
    assert surviving.label == "WARM PAD"
    assert isinstance(surviving.anchor, ModuleSlotAnchor)
    assert surviving.anchor.occurrence.module_hash == module.hash


def test_reset_library_leaves_the_schema_usable_afterward(connection: Connection, populated_library: Path) -> None:
    library_root = populated_library

    reset_library(connection, library_root)
    connection.commit()

    module_repository = PostgresModuleRepository(connection)
    module_repository.insert(
        Module(
            hash=format(1, "064x"),
            id=module_repository.next_id(),
            filename="fresh.it",
            tracker=TrackerFormat.IT,
            title="fresh",
            channel_count=4,
            pattern_count=1,
            instrument_count=1,
            sample_count=1,
            file_size=1024,
            ingested_at=datetime.now(UTC),
        )
    )
    connection.commit()

    assert connection.execute(select(func.count()).select_from(metadata.tables["module"])).scalar_one() == 1


def test_a_reset_a_reader_holds_off_is_refused_and_leaves_every_row(
    connection: Connection, populated_library: Path, _database_url: str
) -> None:
    before = _row_counts(connection)
    reader = connect(_database_url, read_only=True)
    reader.execute(select(func.count()).select_from(metadata.tables["sample"])).scalar_one()

    with pytest.raises(ResetRefused, match="held the catalog"):
        reset_library(connection, populated_library, lock_timeout_milliseconds=200)
    reader.close()

    assert _row_counts(connection) == before
    assert any((populated_library / "objects").rglob("*.wav"))


def test_a_reset_removes_what_a_stopped_reset_left_aside(connection: Connection, populated_library: Path) -> None:
    left_aside = populated_library / f"objects{RETIRED_SUFFIX}"
    left_aside.mkdir()
    (left_aside / "stale.wav").write_bytes(b"stale")

    reset_library(connection, populated_library)

    assert not left_aside.exists()
    assert list((populated_library / "objects").iterdir()) == []


def test_a_reset_catalog_numbers_its_modules_from_one_again(connection: Connection, populated_library: Path) -> None:
    reset_library(connection, populated_library)

    assert PostgresModuleRepository(connection).next_id() == 1
