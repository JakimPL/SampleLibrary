from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Connection

from samplecore.config import LibraryConfig
from samplecore.hashing import compute_module_hash
from samplecore.progress import tracked
from samplecore.storage.database import share_extraction_lock, start_batch
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.note_extraction import PostgresModuleNoteExtractionRepository
from sampleextract.discovery import FORMAT_LOADERS, discover_modules
from sampleextract.notes.persistence import clear_module_notes, persist_module_notes
from sampleextract.parsing import RECOVERABLE_MODULE_ERRORS, ExtractionFailure, FailureStage, parse_module


@dataclass(frozen=True)
class NoteExtractionSummary:
    """What one note-extraction pass did, across every module file it discovered."""

    discovered: int
    read: int
    already_extracted: int
    duplicate_files: int
    note_events: int
    failures: tuple[ExtractionFailure, ...]


def extract_missing_notes(config: LibraryConfig, connection: Connection, *, force: bool) -> NoteExtractionSummary:
    """Read the patterns of every cataloged module whose notes are not yet on file.

    A module is found by hashing the file and looking the hash up, the same way ingest recognizes
    one, so this holds wherever a collection keeps its files. A catalog holds one module per content
    hash while a collection may keep the same bytes under several paths, so every module this pass
    reads is remembered as it goes and a later file naming it is counted as the duplicate it is.
    Each module lands in a transaction of its own, which is what lets an interrupted pass resume
    having lost at most the module it was reading. ``force`` reads every module again, clearing what
    an earlier pass left behind first. A file that cannot be read is recorded as a failure, and the
    pass holds the extraction lock in shared mode while it runs, as extraction does.

    Raises:
        FileNotFoundError: the source directory does not exist.
        NotADirectoryError: the source directory names a file.
    """
    share_extraction_lock(connection)
    module_repository = PostgresModuleRepository(connection)
    extracted_before = PostgresModuleNoteExtractionRepository(connection).extracted_module_ids()
    paths = discover_modules(config.module_source_directory).paths
    failures: list[ExtractionFailure] = []
    read_module_ids: set[int] = set()
    note_events = 0
    duplicate_files = 0
    already_extracted = 0
    for path in tracked(paths, total=len(paths), label="Reading module notes"):
        try:
            data = path.read_bytes()
        except OSError as error:
            failures.append(ExtractionFailure(path=path, stage=FailureStage.READ, reason=str(error)))
            continue

        module = module_repository.get(compute_module_hash(data))
        if module is None:
            continue  # a file the catalog does not hold, which this pass has nothing to attach to

        if module.id in read_module_ids:
            duplicate_files += 1
            continue

        if module.id in extracted_before and not force:
            already_extracted += 1
            continue

        try:
            song = parse_module(data, tracker=FORMAT_LOADERS[path.suffix.lower()])
        except RECOVERABLE_MODULE_ERRORS as error:
            failures.append(ExtractionFailure(path=path, stage=FailureStage.PARSE, reason=str(error)))
            continue

        with start_batch(connection):
            if module.id in extracted_before:
                clear_module_notes(connection, module_id=module.id)

            note_events += persist_module_notes(
                connection,
                song=song,
                module_id=module.id,
                extracted_at=datetime.now(UTC),
            )

        read_module_ids.add(module.id)

    return NoteExtractionSummary(
        discovered=len(paths),
        read=len(read_module_ids),
        already_extracted=already_extracted,
        duplicate_files=duplicate_files,
        note_events=note_events,
        failures=tuple(failures),
    )
