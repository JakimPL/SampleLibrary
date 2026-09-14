from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from samplecore.config import LibraryConfig
from samplecore.models.scalars import WorkerCount
from sampleextract.discovery import Discovery, discover_modules
from sampleextract.parallel.supervisor import WorkList, cover_in_shares
from sampleextract.run import ExtractionSummary, run_extraction

EXTRACTION_DESCRIPTION: Final[str] = "Extracting modules"


@dataclass(frozen=True)
class CorpusOutcome:
    """What a pass over the whole corpus did: the listing it covered, what the shares that finished
    reported, and the error each share that stopped raised."""

    discovery: Discovery
    summary: ExtractionSummary
    worker_errors: tuple[BaseException, ...]


def extract_corpus(config: LibraryConfig, *, workers: WorkerCount) -> CorpusOutcome:
    """Cover the configured source directory once, spending ``workers`` processes on it.

    Raises:
        FileNotFoundError: the source directory does not exist.
        NotADirectoryError: the source directory names a file.
    """
    discovery = discover_modules(config.module_source_directory)
    outcome = cover_in_shares(
        config,
        WorkList(items=discovery.paths, description=EXTRACTION_DESCRIPTION, noun="modules"),
        workers=workers,
        cover=run_extraction,
        combine=ExtractionSummary.combine,
    )
    return CorpusOutcome(discovery=discovery, summary=outcome.summary, worker_errors=outcome.worker_errors)
