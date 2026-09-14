from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecore.config import LibraryConfig
from samplecore.models.sample_file import SampleFileLocation
from samplecore.storage.database import connect, share_extraction_lock
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_file import PostgresSampleFileRepository
from sampleextract.files.discovery import SampleFileDiscovery
from sampleextract.files.prune import gone_sample_files, prune_gone_sample_files
from sampleextract.files.run import SampleFileScanSummary
from sampleextract.files.scan import SampleFileScanOutcome, scan_sample_directories
from sampleextract.parsing import ExtractionFailure, FailureStage
from sampleextract.prune import PruneRefused
from tests.sampleextract.files.conftest import SamplePack


def _location(sample_pack: SamplePack, path: Path) -> SampleFileLocation:
    return SampleFileLocation(
        directory=sample_pack.directory, relative_path=path.relative_to(sample_pack.directory).as_posix()
    )


@pytest.fixture
def scanned(connection: Connection, files_config: LibraryConfig) -> SampleFileScanOutcome:
    return scan_sample_directories(files_config, workers=1)


@dataclass(frozen=True)
class RefusalCase:
    failures: tuple[ExtractionFailure, ...]
    unreadable_directories: tuple[Path, ...]
    missing_directories: tuple[Path, ...]
    worker_errors: tuple[BaseException, ...]
    reason: str


@pytest.mark.parametrize(
    "case",
    [
        RefusalCase((), (), (), (RuntimeError("a worker stopped"),), reason="worker"),
        RefusalCase((), (Path("/packs/locked"),), (), (), reason="could not be read"),
        RefusalCase(
            (ExtractionFailure(path=Path("/packs/kick.wav"), stage=FailureStage.READ, reason="denied"),),
            (),
            (),
            (),
            reason="could not be read",
        ),
        RefusalCase((), (), (Path("/unplugged"),), (), reason="not there"),
    ],
    ids=("a worker stopped", "an unreadable folder", "an unreadable file", "a missing directory"),
)
def test_a_scan_that_could_not_see_everything_names_no_file_as_gone(
    connection: Connection, files_config: LibraryConfig, scanned: SampleFileScanOutcome, case: RefusalCase
) -> None:
    incomplete = SampleFileScanOutcome(
        discovery=SampleFileDiscovery(
            locations=scanned.discovery.locations,
            missing_directories=case.missing_directories,
            unreadable_directories=case.unreadable_directories,
        ),
        summary=SampleFileScanSummary.combine(
            (scanned.summary, SampleFileScanSummary(0, 0, 0, 0, case.failures, frozenset()))
        ),
        worker_errors=case.worker_errors,
    )

    with pytest.raises(PruneRefused, match=case.reason):
        gone_sample_files(connection, files_config, incomplete)


def test_deleted_and_excluded_files_are_gone_and_the_rest_stay(
    connection: Connection, files_config: LibraryConfig, sample_pack: SamplePack, scanned: SampleFileScanOutcome
) -> None:
    sample_pack.kick.unlink()
    excluding_loops = files_config.model_copy(update={"sample_exclusions": ("*loops*",)})

    gone = gone_sample_files(connection, excluding_loops, scan_sample_directories(excluding_loops, workers=1))

    assert gone == {_location(sample_pack, sample_pack.kick), _location(sample_pack, sample_pack.loop)}


def test_every_file_under_a_directory_the_configuration_no_longer_lists_is_gone(
    connection: Connection, files_config: LibraryConfig, scanned: SampleFileScanOutcome
) -> None:
    without_directories = files_config.model_copy(update={"sample_directories": ()})

    gone = gone_sample_files(connection, without_directories, scan_sample_directories(without_directories, workers=1))

    assert gone == scanned.summary.present_locations


def test_a_directory_left_empty_while_its_files_are_cataloged_is_refused(
    connection: Connection, files_config: LibraryConfig, sample_pack: SamplePack, scanned: SampleFileScanOutcome
) -> None:
    for path in sample_pack.directory.rglob("*"):
        if path.is_file():
            path.unlink()

    with pytest.raises(PruneRefused, match="holds no sample file"):
        gone_sample_files(connection, files_config, scan_sample_directories(files_config, workers=1))


def test_pruning_removes_the_gone_files_and_the_samples_nothing_else_holds(
    connection: Connection, files_config: LibraryConfig, sample_pack: SamplePack, scanned: SampleFileScanOutcome
) -> None:
    kick = PostgresSampleFileRepository(connection).get(_location(sample_pack, sample_pack.kick))
    assert kick is not None
    sample_pack.kick.unlink()

    summary = prune_gone_sample_files(files_config, connection, scan_sample_directories(files_config, workers=1))

    assert (summary.sample_files_removed, summary.samples_removed) == (1, 1)
    assert PostgresSampleRepository(connection).get(kick.sample_hash) is None


def test_a_prune_is_refused_while_another_pass_adds_to_the_catalog(
    connection: Connection, _database_url: str, files_config: LibraryConfig, scanned: SampleFileScanOutcome
) -> None:
    extracting = connect(_database_url)
    try:
        share_extraction_lock(extracting)
        with pytest.raises(PruneRefused, match="another"):
            prune_gone_sample_files(files_config, connection, scanned)
    finally:
        extracting.close()
