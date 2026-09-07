from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Connection
from tqdm import tqdm

from samplecore.config import LibraryConfig
from samplecore.hashing import compute_module_hash
from samplecore.models.module import Module
from samplecore.storage.repositories.module import PostgresModuleRepository
from sampleextract.discovery import FORMAT_LOADERS, discover_modules
from sampleextract.ingest import ingest_module
from sampleextract.parsing import RECOVERABLE_PARSE_ERRORS, ExtractionFailure, parse_module


@dataclass(frozen=True)
class ExtractionSummary:
    """What one extraction run did, across every module it discovered."""

    discovered: int
    ingested: tuple[Module, ...]
    skipped_existing: int
    failures: tuple[ExtractionFailure, ...]


def run_extraction(config: LibraryConfig, connection: Connection) -> ExtractionSummary:
    """Discover every readable module under the configured source directory and ingest each once.

    A module already known by its hash is skipped before it is parsed, so a repeat run over an
    unchanged corpus costs one hash and one indexed lookup per file, never a re-parse. A file that
    fails to parse is recorded as a failure and the run continues over the rest of the corpus.
    """
    module_repository = PostgresModuleRepository(connection)
    paths = discover_modules(config.module_source_directory)
    ingested: list[Module] = []
    failures: list[ExtractionFailure] = []
    skipped_existing = 0
    for path in tqdm(paths, desc="Extracting modules"):
        data = path.read_bytes()
        module_hash = compute_module_hash(data)
        if module_repository.get(module_hash) is not None:
            skipped_existing += 1
            continue

        try:
            ingested.append(_ingest_one(connection, config, path=path, data=data, module_hash=module_hash))
        except RECOVERABLE_PARSE_ERRORS as error:
            failures.append(ExtractionFailure(path=path, reason=str(error)))

    return ExtractionSummary(
        discovered=len(paths), ingested=tuple(ingested), skipped_existing=skipped_existing, failures=tuple(failures)
    )


def _ingest_one(connection: Connection, config: LibraryConfig, *, path: Path, data: bytes, module_hash: str) -> Module:
    tracker = FORMAT_LOADERS[path.suffix.lower()]
    song = parse_module(data, tracker=tracker)
    return ingest_module(
        connection,
        config.library_root,
        module_hash=module_hash,
        tracker=tracker,
        filename=path.name,
        file_size=len(data),
        song=song,
        ingested_at=datetime.now(UTC),
        minimum_sample_frames=config.minimum_sample_frames,
    )
