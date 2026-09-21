from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from samplecore.config import LibraryConfig
from samplecore.models.scalars import WorkerCount
from sampleextract.files.discovery import SampleFileDiscovery, discover_sample_files
from sampleextract.files.run import SampleFileScanSummary, scan_sample_files
from sampleextract.parallel.supervisor import WorkList, cover_in_shares

SCAN_DESCRIPTION: Final[str] = "Scanning sample files"


@dataclass(frozen=True)
class SampleFileScanOutcome:
    """What a scan of every configured sample directory did: the listing it covered, what the shares
    that finished reported, and the error each share that stopped raised."""

    discovery: SampleFileDiscovery
    summary: SampleFileScanSummary
    worker_errors: tuple[BaseException, ...]


def scan_sample_directories(config: LibraryConfig, *, workers: WorkerCount) -> SampleFileScanOutcome:
    """Cover every configured sample directory once, spending ``workers`` processes on it.

    A directory that is missing is named in the outcome and the others are scanned all the same,
    since one unplugged drive leaves every other folder of samples as worth cataloging as before.
    """
    discovery = discover_sample_files(config.sample_directories, exclusions=config.sample_exclusions)
    outcome = cover_in_shares(
        config,
        WorkList(items=discovery.locations, description=SCAN_DESCRIPTION, noun="sample files"),
        workers=workers,
        cover=scan_sample_files,
        combine=SampleFileScanSummary.combine,
    )
    return SampleFileScanOutcome(discovery=discovery, summary=outcome.summary, worker_errors=outcome.worker_errors)
