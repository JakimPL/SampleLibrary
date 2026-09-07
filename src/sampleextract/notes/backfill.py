from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Connection
from tqdm import tqdm

from samplecore.config import LibraryConfig
from samplecore.hashing import compute_module_hash
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.note_extraction import PostgresModuleNoteExtractionRepository
from sampleextract.discovery import FORMAT_LOADERS, discover_modules
from sampleextract.notes.persistence import clear_module_notes, persist_module_notes
from sampleextract.parsing import RECOVERABLE_PARSE_ERRORS, ExtractionFailure, parse_module


@dataclass(frozen=True)
class NoteExtractionSummary:
    """What one note-extraction pass did, across every module it discovered."""

    discovered: int
    read: int
    already_extracted: int
    note_events: int
    failures: tuple[ExtractionFailure, ...]


def extract_missing_notes(config: LibraryConfig, connection: Connection, *, force: bool) -> NoteExtractionSummary:
    """Read the patterns of every catalogued module whose notes are not yet on file.

    A module is found by hashing the file and looking the hash up, the same way ingest recognises
    one, so this holds wherever a collection keeps its files. Each module lands in a transaction of
    its own, which is what lets an interrupted pass resume having lost at most the module it was
    reading. ``force`` reads every module again, clearing what an earlier pass left behind first.
    """
    module_repository = PostgresModuleRepository(connection)
    extracted_module_ids = PostgresModuleNoteExtractionRepository(connection).extracted_module_ids()
    paths = discover_modules(config.module_source_directory)
    failures: list[ExtractionFailure] = []
    note_events = 0
    read = 0
    already_extracted = 0
    for path in tqdm(paths, desc="Reading module notes"):
        data = path.read_bytes()
        module = module_repository.get(compute_module_hash(data))
        if module is None:
            continue  # a file the catalog does not hold, which this pass has nothing to attach to

        if module.id in extracted_module_ids and not force:
            already_extracted += 1
            continue

        try:
            song = parse_module(data, tracker=FORMAT_LOADERS[path.suffix.lower()])
        except RECOVERABLE_PARSE_ERRORS as error:
            failures.append(ExtractionFailure(path=path, reason=str(error)))
            continue

        with start_batch(connection):
            if module.id in extracted_module_ids:
                clear_module_notes(connection, module_id=module.id)

            note_events += persist_module_notes(
                connection,
                song=song,
                module_id=module.id,
                extracted_at=datetime.now(UTC),
                minimum_sample_frames=config.minimum_sample_frames,
            )

        read += 1

    return NoteExtractionSummary(
        discovered=len(paths),
        read=read,
        already_extracted=already_extracted,
        note_events=note_events,
        failures=tuple(failures),
    )
