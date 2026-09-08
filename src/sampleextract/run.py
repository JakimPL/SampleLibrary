from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Connection
from sqlalchemy.exc import IntegrityError
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
    ingested_elsewhere: int
    failures: tuple[ExtractionFailure, ...]


def run_extraction(config: LibraryConfig, connection: Connection) -> ExtractionSummary:
    """Discover every readable module under the configured source directory and ingest each once.

    A module already known by its hash is skipped before it is parsed, so a repeat run over an
    unchanged corpus costs one hash and one indexed lookup per file, never a re-parse. A file that
    fails to parse is recorded as a failure and the run continues over the rest of the corpus.

    Several runs may share one catalog, each over its own shard. Two of them can hold copies of the
    same module under different names -- this corpus has hundreds of such pairs -- and reach it at
    the same moment, both finding it unknown and both inserting. The catalog's own uniqueness on the
    module hash settles which one lands; the other rolls its whole module back and counts under
    ``ingested_elsewhere``, having done work that turned out to be someone else's. What tells the
    two apart is the catalog holding the module afterwards: no other route could have put it there,
    since this run had just found it absent.
    """
    module_repository = PostgresModuleRepository(connection)
    paths = discover_modules(config.module_source_directory)
    ingested: list[Module] = []
    failures: list[ExtractionFailure] = []
    skipped_existing = 0
    ingested_elsewhere = 0
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
        except IntegrityError:
            if module_repository.get(module_hash) is None:
                raise

            ingested_elsewhere += 1

    return ExtractionSummary(
        discovered=len(paths),
        ingested=tuple(ingested),
        skipped_existing=skipped_existing,
        ingested_elsewhere=ingested_elsewhere,
        failures=tuple(failures),
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
