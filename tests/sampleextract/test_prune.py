from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecore.config import LibraryConfig
from samplecore.storage.database import connect, share_extraction_lock
from sampleextract.discovery import Discovery
from sampleextract.parallel.supervisor import CorpusOutcome
from sampleextract.parsing import ExtractionFailure, FailureStage
from sampleextract.prune import PruneRefused, gone_modules, prune_gone_modules
from sampleextract.run import ExtractionSummary

MODULE_PATH = Path("modules/song.xm")


def _outcome(
    *,
    paths: tuple[Path, ...] = (MODULE_PATH,),
    unreadable_directories: tuple[Path, ...] = (),
    failures: tuple[ExtractionFailure, ...] = (),
    worker_errors: tuple[BaseException, ...] = (),
) -> CorpusOutcome:
    return CorpusOutcome(
        discovery=Discovery(paths=paths, unreadable_directories=unreadable_directories),
        summary=ExtractionSummary(
            discovered=len(paths),
            ingested=(),
            skipped_existing=0,
            ingested_elsewhere=0,
            failures=failures,
            present_module_hashes=frozenset(),
        ),
        worker_errors=worker_errors,
    )


@pytest.mark.parametrize(
    "outcome",
    [
        _outcome(worker_errors=(RuntimeError("a worker stopped"),)),
        _outcome(unreadable_directories=(Path("modules/locked"),)),
        _outcome(failures=(ExtractionFailure(path=MODULE_PATH, stage=FailureStage.READ, reason="permission denied"),)),
    ],
    ids=("a worker stopped", "an unreadable folder", "an unreadable file"),
)
def test_a_pass_that_could_not_see_everything_names_no_module_as_gone(
    connection: Connection, outcome: CorpusOutcome
) -> None:
    with pytest.raises(PruneRefused):
        gone_modules(connection, outcome)


def test_a_file_that_failed_to_parse_still_counts_as_present(connection: Connection) -> None:
    outcome = _outcome(failures=(ExtractionFailure(path=MODULE_PATH, stage=FailureStage.PARSE, reason="bad tag"),))

    assert gone_modules(connection, outcome).module_hashes == frozenset()


def test_a_prune_is_refused_while_another_pass_adds_to_the_catalog(
    connection: Connection, _database_url: str, tmp_path: Path
) -> None:
    config = LibraryConfig(module_source_directory=tmp_path, library_root=tmp_path, database_url=_database_url)
    extracting = connect(_database_url)
    try:
        share_extraction_lock(extracting)
        with pytest.raises(PruneRefused, match="another"):
            prune_gone_modules(config, connection, _outcome())
    finally:
        extracting.close()
