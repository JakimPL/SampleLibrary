from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Connection
from sqlalchemy.exc import IntegrityError

from samplecore.config import LibraryConfig
from samplecore.hashing import compute_module_hash
from samplecore.models.module import Module
from samplecore.storage.database import share_extraction_lock
from samplecore.storage.repositories.module import PostgresModuleRepository
from sampleextract.discovery import FORMAT_LOADERS
from sampleextract.ingest import ingest_module
from sampleextract.parsing import RECOVERABLE_MODULE_ERRORS, ExtractionFailure, FailureStage, parse_module
from sampleextract.progress import ProgressSink


@dataclass(frozen=True)
class ExtractionSummary:
    """What one extraction pass did, across the modules it covered.

    ``present_module_hashes`` holds the hash of every file the pass read, whether or not its module
    made it into the catalog, which is what tells a module whose file is gone from one whose file
    merely failed to parse.
    """

    discovered: int
    ingested: tuple[Module, ...]
    skipped_existing: int
    ingested_elsewhere: int
    failures: tuple[ExtractionFailure, ...]
    present_module_hashes: frozenset[str]

    @classmethod
    def combine(cls, summaries: Iterable[ExtractionSummary]) -> ExtractionSummary:
        """Several shares' summaries read as the one pass they made up between them."""
        collected = tuple(summaries)
        return cls(
            discovered=sum(summary.discovered for summary in collected),
            ingested=tuple(module for summary in collected for module in summary.ingested),
            skipped_existing=sum(summary.skipped_existing for summary in collected),
            ingested_elsewhere=sum(summary.ingested_elsewhere for summary in collected),
            failures=tuple(failure for summary in collected for failure in summary.failures),
            present_module_hashes=frozenset().union(*(summary.present_module_hashes for summary in collected)),
        )


@dataclass(frozen=True)
class _ReadModule:
    """One module file as a pass read it: where it lies, its bytes, and the hash they carry."""

    path: Path
    data: bytes
    module_hash: str


@dataclass(frozen=True)
class _Tally:
    ingested: list[Module]
    failures: list[ExtractionFailure]
    present_module_hashes: set[str]


def run_extraction(
    config: LibraryConfig, connection: Connection, paths: tuple[Path, ...], *, progress: ProgressSink
) -> ExtractionSummary:
    """Ingest each of ``paths`` once, reporting what the pass covered.

    ``paths`` is the share this pass is to cover, which lets one caller hand the whole corpus to a
    single pass and another split it between several. ``discovered`` counts what this share holds.

    A module already known by its hash is skipped before it is parsed, so a repeat pass over an
    unchanged corpus costs one hash and one indexed lookup per file. A file that cannot be read, a
    module whose format does not parse, and a module whose content the catalog refuses are each
    recorded as a failure at their own stage, and the pass continues over the rest of its share. A
    failure of the library itself, such as a full disk under the content store or a lost database
    connection, ends the pass, since every module after it would meet the same.

    Several passes may share one catalog. Two of them can hold copies of the same module under
    different names -- this corpus has hundreds of such pairs -- and reach it at the same moment,
    both finding it unknown and both inserting. The catalog's own uniqueness on the module hash
    settles which one lands; the other rolls its whole module back and counts under
    ``ingested_elsewhere``, having done work that turned out to be someone else's. What tells the
    two apart is the catalog holding the module afterwards: no other route could have put it there,
    since this pass had just found it absent. Every pass holds the extraction lock in shared mode
    while it runs, which keeps a prune from removing what it is adding.
    """
    share_extraction_lock(connection)
    module_repository = PostgresModuleRepository(connection)
    tally = _Tally(ingested=[], failures=[], present_module_hashes=set())
    skipped_existing = 0
    ingested_elsewhere = 0
    for path in paths:
        try:
            data = path.read_bytes()
        except OSError as error:
            tally.failures.append(ExtractionFailure(path=path, stage=FailureStage.READ, reason=str(error)))
        else:
            module_hash = compute_module_hash(data)
            tally.present_module_hashes.add(module_hash)
            if module_repository.get(module_hash) is not None:
                skipped_existing += 1
            elif not _cover_one(connection, config, _ReadModule(path, data, module_hash), tally=tally):
                ingested_elsewhere += 1

        progress.advance(1)

    return ExtractionSummary(
        discovered=len(paths),
        ingested=tuple(tally.ingested),
        skipped_existing=skipped_existing,
        ingested_elsewhere=ingested_elsewhere,
        failures=tuple(tally.failures),
        present_module_hashes=frozenset(tally.present_module_hashes),
    )


def _cover_one(connection: Connection, config: LibraryConfig, found: _ReadModule, *, tally: _Tally) -> bool:
    """Parse and ingest one module this pass found unknown, reporting ``False`` when another pass landed it first."""
    tracker = FORMAT_LOADERS[found.path.suffix.lower()]
    try:
        song = parse_module(found.data, tracker=tracker)
    except RECOVERABLE_MODULE_ERRORS as error:
        tally.failures.append(ExtractionFailure(path=found.path, stage=FailureStage.PARSE, reason=str(error)))
        return True

    try:
        tally.ingested.append(
            ingest_module(
                connection,
                config.library_root,
                module_hash=found.module_hash,
                tracker=tracker,
                filename=found.path.name,
                file_size=len(found.data),
                song=song,
                ingested_at=datetime.now(UTC),
                minimum_sample_frames=config.minimum_sample_frames,
            )
        )
    except RECOVERABLE_MODULE_ERRORS as error:
        tally.failures.append(ExtractionFailure(path=found.path, stage=FailureStage.CATALOG, reason=str(error)))
    except IntegrityError:
        if PostgresModuleRepository(connection).get(found.module_hash) is None:
            raise
        return False
    return True
