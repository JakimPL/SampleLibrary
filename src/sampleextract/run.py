from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import duckdb
from tqdm import tqdm

from samplecore.config import LibraryConfig
from samplecore.hashing import compute_module_hash
from samplecore.models.module import Module
from samplecore.storage.repositories.module import DuckDBModuleRepository
from sampleextract.discovery import FORMAT_LOADERS, discover_modules
from sampleextract.ingest import ingest_module
from sampleextract.parsing import parse_module

_RECOVERABLE_PARSE_ERRORS: Final[tuple[type[Exception], ...]] = (ValueError, OSError, struct.error, IndexError)
# ValueError: TrackMod's own documented parse failures (a bad tag, a malformed structure) and every
#   pydantic ValidationError, which subclasses it. OSError: the file could not be read. struct.error and
#   IndexError: raw struct/array bounds failures a sufficiently corrupt file can still trigger beneath
#   TrackMod's own ValueError guards. Anything outside this set is treated as a bug, and crashes loudly.


@dataclass(frozen=True)
class ExtractionFailure:
    """One module a run could not ingest, and why."""

    path: Path
    reason: str


@dataclass(frozen=True)
class ExtractionSummary:
    """What one extraction run did, across every module it discovered."""

    discovered: int
    ingested: tuple[Module, ...]
    skipped_existing: int
    failures: tuple[ExtractionFailure, ...]


def run_extraction(config: LibraryConfig, connection: duckdb.DuckDBPyConnection) -> ExtractionSummary:
    """Discover every readable module under the configured source directory and ingest each once.

    A module already known by its hash is skipped before it is parsed, so a repeat run over an
    unchanged corpus costs one hash and one indexed lookup per file, never a re-parse. A file that
    fails to parse is recorded as a failure and the run continues over the rest of the corpus.
    """
    module_repository = DuckDBModuleRepository(connection)
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
            ingested.append(_ingest_one(connection, config.library_root, path=path, data=data, module_hash=module_hash))
        except _RECOVERABLE_PARSE_ERRORS as error:
            failures.append(ExtractionFailure(path=path, reason=str(error)))

    return ExtractionSummary(
        discovered=len(paths), ingested=tuple(ingested), skipped_existing=skipped_existing, failures=tuple(failures)
    )


def _ingest_one(
    connection: duckdb.DuckDBPyConnection, library_root: Path, *, path: Path, data: bytes, module_hash: str
) -> Module:
    tracker = FORMAT_LOADERS[path.suffix.lower()]
    song = parse_module(data, tracker=tracker)
    return ingest_module(
        connection,
        library_root,
        module_hash=module_hash,
        tracker=tracker,
        filename=path.name,
        file_size=len(data),
        song=song,
        ingested_at=datetime.now(UTC),
    )
