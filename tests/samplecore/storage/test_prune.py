from __future__ import annotations

from pathlib import Path

from sqlalchemy import Connection, ForeignKey, func, select

from samplecore.models.annotation import AnnotationSource, SampleAnnotation
from samplecore.models.sample_properties import SampleOccurrence
from samplecore.storage import audio_store
from samplecore.storage.atomic import PARTIAL_SUFFIX
from samplecore.storage.database import (
    metadata,
    module,
    module_cloud_coordinates,
    sample,
    sample_properties,
    sample_relation,
)
from samplecore.storage.prune import MODULE_ROW_TABLES, SAMPLE_ROW_TABLES, prune_modules
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository


def _hashes(connection: Connection, column_owner: str) -> set[str]:
    table = metadata.tables[column_owner]
    return {str(row[0]) for row in connection.execute(select(table.c.hash))}


def test_every_table_referring_to_a_module_or_a_sample_is_pruned_through() -> None:
    """A table added to the catalog later is either named here or left holding rows of a pruned module."""
    pruned_through = {*MODULE_ROW_TABLES, *SAMPLE_ROW_TABLES, sample_relation, module_cloud_coordinates}
    referring = {
        table
        for table in metadata.sorted_tables
        for foreign_key in table.foreign_keys
        if isinstance(foreign_key, ForeignKey) and foreign_key.column.table in (module, sample, sample_properties)
    }

    assert referring <= pruned_through


def test_pruning_a_module_removes_it_and_the_samples_no_other_module_holds(
    connection: Connection, populated_library: Path
) -> None:
    modules = PostgresModuleRepository(connection).list_all()
    gone = modules[0]
    held_elsewhere = {
        str(row.sample_hash)
        for row in connection.execute(
            select(sample_properties.c.sample_hash).where(sample_properties.c.module_id != gone.id)
        )
    }
    held_by_gone = {
        str(row.sample_hash)
        for row in connection.execute(
            select(sample_properties.c.sample_hash).where(sample_properties.c.module_id == gone.id)
        )
    }
    orphans = held_by_gone - held_elsewhere

    summary = prune_modules(connection, populated_library, module_hashes=frozenset({gone.hash}))

    assert summary.modules_removed == 1
    assert gone.hash not in _hashes(connection, "module")
    remaining_samples = _hashes(connection, "sample")
    assert not orphans & remaining_samples
    assert held_elsewhere <= remaining_samples
    for orphan in orphans:
        assert not audio_store.object_path(populated_library, orphan).exists()
    for table in MODULE_ROW_TABLES:
        assert (
            connection.execute(select(func.count()).select_from(table).where(table.c.module_id == gone.id)).scalar_one()
            == 0
        )


def test_pruning_leaves_hand_annotations_for_relinking(connection: Connection, populated_library: Path) -> None:
    gone = PostgresModuleRepository(connection).list_all()[0]
    occurrence = connection.execute(select(sample_properties).where(sample_properties.c.module_id == gone.id)).first()
    assert occurrence is not None
    annotations = PostgresSampleAnnotationRepository(connection)
    annotations.upsert_many(
        (
            SampleAnnotation(
                sample_hash=occurrence.sample_hash,
                label="kick",
                rating=None,
                favorite=False,
                occurrence=SampleOccurrence(
                    module_hash=gone.hash,
                    instrument_index=occurrence.instrument_index,
                    sample_slot=occurrence.sample_slot,
                ),
                module_filename=gone.filename,
                sample_name=occurrence.name,
                source=AnnotationSource.SAMPLE,
                annotated_at=gone.ingested_at,
            ),
        )
    )
    connection.commit()

    prune_modules(connection, populated_library, module_hashes=frozenset({gone.hash}))

    assert annotations.get(occurrence.sample_hash) is not None


def test_pruning_sweeps_leftover_partial_files_and_objects_nothing_names(
    connection: Connection, populated_library: Path
) -> None:
    objects = populated_library / audio_store.OBJECTS_DIRECTORY_NAME
    stray = objects / "ff" / f"{'f' * 64}.wav"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(b"left behind")
    partial = objects / "ff" / f"tmp1234{PARTIAL_SUFFIX}"
    partial.write_bytes(b"half")

    summary = prune_modules(connection, populated_library, module_hashes=frozenset())

    assert summary.objects_removed == 1
    assert not stray.exists()
    assert not partial.exists()
