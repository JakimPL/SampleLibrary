from __future__ import annotations

from sqlalchemy import Connection

from samplecore.config import LibraryConfig
from samplecore.models.sample_file import SampleFile, SampleFileLocation
from samplecore.storage.database import claim_extraction_lock
from samplecore.storage.prune import SampleFilePruneSummary, prune_sample_files
from samplecore.storage.repositories.sample_file import PostgresSampleFileRepository
from sampleextract.files.scan import SampleFileScanOutcome
from sampleextract.parsing import FailureStage
from sampleextract.prune import PruneRefused


def gone_sample_files(
    connection: Connection, config: LibraryConfig, outcome: SampleFileScanOutcome
) -> frozenset[SampleFileLocation]:
    """The cataloged sample files the scan found no longer belonging, once the scan is complete enough to say so.

    A file belongs while the scan found it present (see ``SampleFileScanSummary``). The rest are gone:
    files deleted from a directory, files an exclusion now names, and every file under a directory
    the configuration no longer lists, since the configuration is what declares the collection.

    Raises:
        PruneRefused: a share stopped, a file or folder could not be read, a configured directory is
            missing, or a configured directory yielded no sample file while the catalog holds files
            under it, as the empty mount point of an unmounted drive does.
    """
    if outcome.worker_errors:
        raise PruneRefused("a worker stopped partway, so the scan missed files it would have read")
    unreadable = [failure.path for failure in outcome.summary.failures if failure.stage is FailureStage.READ]
    if unreadable or outcome.discovery.unreadable_directories:
        named = [*outcome.discovery.unreadable_directories, *unreadable]
        raise PruneRefused(f"{len(named)} file(s) or folder(s) could not be read, among them {named[0]}")
    if outcome.discovery.missing_directories:
        raise PruneRefused(f"the sample directory {outcome.discovery.missing_directories[0]} is not there")

    cataloged = PostgresSampleFileRepository(connection).list_all()
    _refuse_an_emptied_directory(config, outcome, cataloged)
    return frozenset(
        sample_file.location
        for sample_file in cataloged
        if sample_file.location not in outcome.summary.present_locations
    )


def prune_gone_sample_files(
    config: LibraryConfig, connection: Connection, outcome: SampleFileScanOutcome
) -> SampleFilePruneSummary:
    """Remove the sample files that are gone, and the samples neither a module nor a file still holds.

    Raises:
        PruneRefused: the scan leaves the gone files uncertain (see ``gone_sample_files``), or another
            extraction, scan or note-reading pass is running on the same catalog.
    """
    gone = gone_sample_files(connection, config, outcome)
    if not claim_extraction_lock(connection):
        raise PruneRefused("another extraction, scan or note-reading pass is running on this catalog")
    return prune_sample_files(connection, config.library_root, locations=gone)


def _refuse_an_emptied_directory(
    config: LibraryConfig, outcome: SampleFileScanOutcome, cataloged: tuple[SampleFile, ...]
) -> None:
    """Refuse when a configured directory yielded nothing while files under it are cataloged.

    Raises:
        PruneRefused: such a directory exists.
    """
    found_in = {location.directory for location in outcome.discovery.locations}
    cataloged_in = {sample_file.location.directory for sample_file in cataloged}
    for directory in config.sample_directories:
        if directory in cataloged_in and directory not in found_in:
            raise PruneRefused(f"the sample directory {directory} holds no sample file while the catalog holds some")
