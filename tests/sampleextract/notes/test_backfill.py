from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Connection
from trackmod.core.notes.pitch import Note

from samplecore.config import LibraryConfig
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.module_instrument import PostgresModuleInstrumentRepository
from samplecore.storage.repositories.note_event import PostgresNoteEventRepository
from sampleextract.discovery import discover_modules
from sampleextract.notes.backfill import extract_missing_notes
from sampleextract.notes.persistence import clear_module_notes
from sampleextract.progress import ProgressSink
from sampleextract.run import run_extraction


@pytest.fixture
def cataloged_corpus(
    connection: Connection,
    config: LibraryConfig,
    xm_module_bytes: bytes,
    it_module_bytes: bytes,
    progress: ProgressSink,
) -> LibraryConfig:
    """Two modules already ingested, with the notes a run of ingest recorded cleared away again.

    Clearing leaves exactly the state a catalog filled before note extraction existed would be in,
    which is what the backfill pass is built to work through.
    """
    (config.module_source_directory / "song.xm").write_bytes(xm_module_bytes)
    (config.module_source_directory / "song.it").write_bytes(it_module_bytes)
    run_extraction(config, connection, discover_modules(config.module_source_directory), progress=progress)
    for module in PostgresModuleRepository(connection).list_all():
        clear_module_notes(connection, module_id=module.id)

    connection.commit()
    return config


def test_a_pass_reads_every_cataloged_module_whose_notes_are_missing(
    connection: Connection, cataloged_corpus: LibraryConfig, played_note: Note
) -> None:
    summary = extract_missing_notes(cataloged_corpus, connection, force=False)

    assert summary.discovered == 2
    assert summary.read == 2
    assert summary.already_extracted == 0
    assert summary.duplicate_files == 0
    assert summary.note_events == 2
    assert summary.failures == ()

    module = PostgresModuleRepository(connection).list_all()[0]
    events = PostgresNoteEventRepository(connection).list_for_module(module.id)
    assert [event.sounded_note for event in events] == [played_note]


def test_a_second_pass_skips_every_module_already_read(connection: Connection, cataloged_corpus: LibraryConfig) -> None:
    extract_missing_notes(cataloged_corpus, connection, force=False)

    summary = extract_missing_notes(cataloged_corpus, connection, force=False)

    assert summary.read == 0
    assert summary.already_extracted == 2
    assert summary.note_events == 0


def test_force_reads_every_module_again_without_duplicating_its_events(
    connection: Connection, cataloged_corpus: LibraryConfig
) -> None:
    extract_missing_notes(cataloged_corpus, connection, force=False)
    before = PostgresNoteEventRepository(connection).count()

    summary = extract_missing_notes(cataloged_corpus, connection, force=True)

    assert summary.read == 2
    assert summary.already_extracted == 0
    assert PostgresNoteEventRepository(connection).count() == before


def test_a_pass_records_the_instrument_slots_each_module_numbers(
    connection: Connection, cataloged_corpus: LibraryConfig
) -> None:
    extract_missing_notes(cataloged_corpus, connection, force=False)

    module = PostgresModuleRepository(connection).list_all()[0]
    instruments = PostgresModuleInstrumentRepository(connection).list_for_module(module.id)

    assert [instrument.name for instrument in instruments] == ["voice"]


def test_the_same_module_kept_under_two_paths_is_read_once(
    connection: Connection, cataloged_corpus: LibraryConfig, xm_module_bytes: bytes
) -> None:
    """A catalog holds one module per content hash, so a second copy of one names a module already read."""
    (cataloged_corpus.module_source_directory / "copy-of-song.xm").write_bytes(xm_module_bytes)

    summary = extract_missing_notes(cataloged_corpus, connection, force=False)

    assert summary.discovered == 3
    assert summary.read == 2
    assert summary.duplicate_files == 1
    assert summary.failures == ()


def test_a_forced_pass_reads_a_duplicated_module_once_as_well(
    connection: Connection, cataloged_corpus: LibraryConfig, xm_module_bytes: bytes
) -> None:
    (cataloged_corpus.module_source_directory / "copy-of-song.xm").write_bytes(xm_module_bytes)
    extract_missing_notes(cataloged_corpus, connection, force=False)

    summary = extract_missing_notes(cataloged_corpus, connection, force=True)

    assert summary.read == 2
    assert summary.duplicate_files == 1


def test_a_file_the_catalog_never_ingested_is_passed_over(
    connection: Connection, cataloged_corpus: LibraryConfig, s3m_module_bytes: bytes
) -> None:
    (cataloged_corpus.module_source_directory / "unknown.s3m").write_bytes(s3m_module_bytes)

    summary = extract_missing_notes(cataloged_corpus, connection, force=False)

    assert summary.discovered == 3
    assert summary.read == 2
    assert summary.failures == ()


def test_ingest_records_a_new_module_s_notes_without_a_backfill_pass(
    connection: Connection, config: LibraryConfig, xm_module_bytes: bytes, played_note: Note, progress: ProgressSink
) -> None:
    (config.module_source_directory / "song.xm").write_bytes(xm_module_bytes)

    summary = run_extraction(config, connection, discover_modules(config.module_source_directory), progress=progress)

    events = PostgresNoteEventRepository(connection).list_for_module(summary.ingested[0].id)
    assert [event.sounded_note for event in events] == [played_note]
