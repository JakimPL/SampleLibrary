from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import Connection

from samplecore.config import LibraryConfig
from samplecore.models.sample_file import FileFingerprint, SampleFileLocation
from samplecore.sample_files.decoding import UNDECODABLE_SAMPLE_FILE_ERRORS, DecodedSampleFile, decode_sample_file
from samplecore.storage.database import share_extraction_lock
from samplecore.storage.repositories.sample_file import PostgresSampleFileRepository
from sampleextract.files.ingest import ingest_sample_file
from sampleextract.parsing import ExtractionFailure, FailureStage
from sampleextract.progress import ProgressSink


@dataclass(frozen=True)
class SampleFileScanSummary:
    """What one scan did, across the sample files it covered.

    ``present_locations`` holds every file the scan found still belonging in the catalog: those it
    cataloged, those unchanged since the last scan, and those whose decoding failed, which keep what
    an earlier scan recorded. A file now shorter than ``minimum_sample_frames`` belongs nowhere, and a
    file that could not be read leaves the scan unsure, which a prune refuses on.
    """

    discovered: int
    cataloged: int
    unchanged: int
    too_short: int
    failures: tuple[ExtractionFailure, ...]
    present_locations: frozenset[SampleFileLocation]

    @classmethod
    def combine(cls, summaries: Iterable[SampleFileScanSummary]) -> SampleFileScanSummary:
        """Several shares' summaries read as the one scan they made up between them."""
        collected = tuple(summaries)
        return cls(
            discovered=sum(summary.discovered for summary in collected),
            cataloged=sum(summary.cataloged for summary in collected),
            unchanged=sum(summary.unchanged for summary in collected),
            too_short=sum(summary.too_short for summary in collected),
            failures=tuple(failure for summary in collected for failure in summary.failures),
            present_locations=frozenset().union(*(summary.present_locations for summary in collected)),
        )


@dataclass
class _Tally:
    cataloged: int
    unchanged: int
    too_short: int
    failures: list[ExtractionFailure]
    present_locations: set[SampleFileLocation]


def scan_sample_files(
    config: LibraryConfig, connection: Connection, locations: tuple[SampleFileLocation, ...], *, progress: ProgressSink
) -> SampleFileScanSummary:
    """Catalog each of ``locations`` in place, reporting what the scan covered.

    A file whose size and write time match what the catalog recorded is passed over unread, so a
    repeat scan of an unchanged collection costs one status call and one indexed lookup per file. A
    file that changed is decoded and cataloged again under what it holds now. A file that cannot be
    read and one that cannot be decoded are each recorded as a failure at their own stage, and the
    scan continues over the rest of its share. The scan holds the extraction lock in shared mode
    while it runs, which keeps a prune from removing what it is adding.
    """
    share_extraction_lock(connection)
    repository = PostgresSampleFileRepository(connection)
    tally = _Tally(cataloged=0, unchanged=0, too_short=0, failures=[], present_locations=set())
    for location in locations:
        _cover_one(config, connection, repository, location, tally=tally)
        progress.advance(1)

    return SampleFileScanSummary(
        discovered=len(locations),
        cataloged=tally.cataloged,
        unchanged=tally.unchanged,
        too_short=tally.too_short,
        failures=tuple(tally.failures),
        present_locations=frozenset(tally.present_locations),
    )


def _cover_one(
    config: LibraryConfig,
    connection: Connection,
    repository: PostgresSampleFileRepository,
    location: SampleFileLocation,
    *,
    tally: _Tally,
) -> None:
    """Take one file in, or pass over it, recording which of those happened."""
    path = location.path
    try:
        fingerprint = FileFingerprint.of(path.stat())
    except OSError as error:
        tally.failures.append(ExtractionFailure(path=path, stage=FailureStage.READ, reason=str(error)))
        return

    cataloged = repository.get(location)
    if cataloged is not None and cataloged.fingerprint == fingerprint:
        tally.unchanged += 1
        tally.present_locations.add(location)
        return

    decoded = _decoded(location, tally=tally)
    if decoded is None:
        return
    if decoded.sample_pcm.sample.frames < config.minimum_sample_frames:
        tally.too_short += 1
        return

    ingest_sample_file(connection, location=location, decoded=decoded, fingerprint=fingerprint)
    tally.cataloged += 1
    tally.present_locations.add(location)


def _decoded(location: SampleFileLocation, *, tally: _Tally) -> DecodedSampleFile | None:
    """The file's sample, or ``None`` with the failure recorded; a file that fails to decode stays present."""
    path = location.path
    try:
        return decode_sample_file(path)
    except OSError as error:
        tally.failures.append(ExtractionFailure(path=path, stage=FailureStage.READ, reason=str(error)))
    except UNDECODABLE_SAMPLE_FILE_ERRORS as error:
        tally.failures.append(ExtractionFailure(path=path, stage=FailureStage.DECODE, reason=str(error)))
        tally.present_locations.add(location)
    return None
