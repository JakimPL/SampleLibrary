from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from sqlalchemy import Connection, Table, delete, exists, or_, select, tuple_

from samplecore.models.sample_file import SampleFileLocation
from samplecore.storage import audio_store
from samplecore.storage.atomic import PARTIAL_SUFFIX
from samplecore.storage.database import (
    HASH_CHUNK_SIZE,
    chunks,
    it_sample_properties,
    module,
    module_cloud_coordinates,
    module_instrument,
    module_note_extraction,
    note_event,
    s3m_sample_properties,
    sample,
    sample_category,
    sample_cloud_coordinates,
    sample_feature_vector,
    sample_file,
    sample_playback_rate,
    sample_properties,
    sample_relation,
    sample_spectral_feature,
    sample_thumbnail,
    start_batch,
    xm_sample_properties,
)

# Every table holding rows of a module, by its `module_id`, children before the tables they refer to.
MODULE_ROW_TABLES: Final[tuple[Table, ...]] = (
    note_event,
    module_note_extraction,
    xm_sample_properties,
    it_sample_properties,
    s3m_sample_properties,
    sample_properties,
    module_instrument,
)
# Every table holding rows of a sample by its `sample_hash`, beside the relations that name it twice.
SAMPLE_ROW_TABLES: Final[tuple[Table, ...]] = (
    sample_cloud_coordinates,
    sample_spectral_feature,
    sample_thumbnail,
    sample_feature_vector,
    sample_category,
    sample_playback_rate,
)
# Every table whose rows keep a sample in the catalog: a sample none of them names is an orphan.
SAMPLE_HOLDER_TABLES: Final[tuple[Table, ...]] = (sample_properties, sample_file)
OBJECT_SUFFIX: Final[str] = ".wav"

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PruneSummary:
    """What one prune removed from the catalog and from the content store."""

    modules_removed: int
    samples_removed: int
    objects_removed: int


@dataclass(frozen=True)
class SampleFilePruneSummary:
    """What one prune of sample files removed from the catalog and from the content store."""

    sample_files_removed: int
    samples_removed: int
    objects_removed: int


def prune_modules(connection: Connection, library_root: Path, *, module_hashes: frozenset[str]) -> PruneSummary:
    """Remove the named modules from the catalog, with every sample neither a module nor a file holds.

    A module leaves together with its occurrences, instruments, notes and cloud placement, in one
    transaction; a sample leaves when no occurrence of it is left in any module and no sample file
    holds it, together with its relations, coordinates, vectors, thumbnail, categories and playback
    rate. Hand annotations stay where they are, in a schema of their own, for `annotations relink` to
    reattach or a person to decide about. Once the transaction commits, the content store lets go of
    every object the catalog no longer names, along with the partial files an interrupted write left,
    so a crash between the two is made good by the next prune.
    """
    module_ids = tuple(
        int(row.id) for row in connection.execute(select(module.c.id).where(module.c.hash.in_(module_hashes)))
    )
    with start_batch(connection):
        for chunk in chunks(module_ids, HASH_CHUNK_SIZE):
            for table in MODULE_ROW_TABLES:
                connection.execute(delete(table).where(table.c.module_id.in_(chunk)))
            connection.execute(
                delete(module_cloud_coordinates).where(
                    module_cloud_coordinates.c.module_hash.in_(select(module.c.hash).where(module.c.id.in_(chunk)))
                )
            )
            connection.execute(delete(module).where(module.c.id.in_(chunk)))
        samples_removed = _remove_orphaned_samples(connection)

    return PruneSummary(
        modules_removed=len(module_ids),
        samples_removed=samples_removed,
        objects_removed=_remove_unnamed_objects(connection, library_root),
    )


def prune_sample_files(
    connection: Connection, library_root: Path, *, locations: frozenset[SampleFileLocation]
) -> SampleFilePruneSummary:
    """Remove the named sample files from the catalog, with every sample neither a module nor a file holds.

    The same removal ``prune_modules`` ends with follows the files, in one transaction, and the content
    store then lets go of what the catalog no longer names.
    """
    ordered = sorted(locations, key=lambda location: location.sort_key)
    sample_files_removed = 0
    with start_batch(connection):
        for chunk in chunks(ordered, HASH_CHUNK_SIZE):
            keys = [(location.directory.as_posix(), location.relative_path) for location in chunk]
            removal = connection.execute(
                delete(sample_file).where(tuple_(sample_file.c.directory, sample_file.c.relative_path).in_(keys))
            )
            sample_files_removed += removal.rowcount
        samples_removed = _remove_orphaned_samples(connection)

    return SampleFilePruneSummary(
        sample_files_removed=sample_files_removed,
        samples_removed=samples_removed,
        objects_removed=_remove_unnamed_objects(connection, library_root),
    )


def _remove_orphaned_samples(connection: Connection) -> int:
    """Remove every sample no module occurrence and no sample file holds, reporting how many left."""
    orphans = _orphaned_sample_hashes(connection)
    for sample_chunk in chunks(orphans, HASH_CHUNK_SIZE):
        _remove_samples(connection, sample_chunk)
    return len(orphans)


def _orphaned_sample_hashes(connection: Connection) -> tuple[str, ...]:
    unheld = (
        ~exists(select(table.c.sample_hash).where(table.c.sample_hash == sample.c.hash))
        for table in SAMPLE_HOLDER_TABLES
    )
    return tuple(str(row.hash) for row in connection.execute(select(sample.c.hash).where(*unheld)))


def _remove_samples(connection: Connection, sample_hashes: Sequence[str]) -> None:
    connection.execute(
        delete(sample_relation).where(
            or_(sample_relation.c.subject_hash.in_(sample_hashes), sample_relation.c.reference_hash.in_(sample_hashes))
        )
    )
    for table in SAMPLE_ROW_TABLES:
        connection.execute(delete(table).where(table.c.sample_hash.in_(sample_hashes)))
    connection.execute(delete(sample).where(sample.c.hash.in_(sample_hashes)))


def _remove_unnamed_objects(connection: Connection, library_root: Path) -> int:
    """Delete every stored object whose hash the catalog no longer holds, and every leftover partial file."""
    objects_directory = library_root / audio_store.OBJECTS_DIRECTORY_NAME
    if not objects_directory.is_dir():
        return 0

    cataloged = {str(row.hash) for row in connection.execute(select(sample.c.hash))}
    removed = 0
    for stored in objects_directory.rglob("*"):
        if not stored.is_file():
            continue
        unnamed = stored.suffix == OBJECT_SUFFIX and stored.stem not in cataloged
        if unnamed or stored.suffix == PARTIAL_SUFFIX:
            stored.unlink(missing_ok=True)
            removed += unnamed
    _logger.info("Removed %d stored object(s) the catalog no longer names.", removed)
    return removed
