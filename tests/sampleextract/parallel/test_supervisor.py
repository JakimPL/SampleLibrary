from __future__ import annotations

from pathlib import Path

from sqlalchemy import Connection
from sqlalchemy.exc import OperationalError

from samplecore.config import LibraryConfig
from samplecore.storage.repositories.module import PostgresModuleRepository
from sampleextract.parallel.supervisor import extract_corpus

WORKER_COUNT = 2
UNREACHABLE_DATABASE_URL = "postgresql+psycopg://nobody:nobody@127.0.0.1:1/absent"


def _config(tmp_path: Path, database_url: str) -> LibraryConfig:
    source = tmp_path / "source"
    source.mkdir()
    return LibraryConfig(module_source_directory=source, library_root=tmp_path / "library", database_url=database_url)


def test_workers_between_them_ingest_the_whole_corpus_exactly_once(
    connection: Connection, _database_url: str, tmp_path: Path, xm_module_bytes: bytes, it_module_bytes: bytes
) -> None:
    """Real processes, one catalog: what they report has to match what the catalog ended up holding."""
    config = _config(tmp_path, _database_url)
    (config.module_source_directory / "first.xm").write_bytes(xm_module_bytes)
    (config.module_source_directory / "second.it").write_bytes(it_module_bytes)

    summary = extract_corpus(config, workers=WORKER_COUNT).summary

    assert summary.discovered == 2
    assert summary.failures == ()
    stored = {module.hash for module in PostgresModuleRepository(connection).list_all()}
    assert stored == {module.hash for module in summary.ingested}
    assert len(stored) == 2


def test_a_single_worker_covers_the_corpus_in_this_process(
    connection: Connection, _database_url: str, tmp_path: Path, xm_module_bytes: bytes
) -> None:
    """One share is one pass, so the common small run starts no subprocess to make it."""
    config = _config(tmp_path, _database_url)
    (config.module_source_directory / "first.xm").write_bytes(xm_module_bytes)

    summary = extract_corpus(config, workers=1).summary

    assert len(summary.ingested) == 1


def test_more_workers_than_modules_still_covers_the_corpus_once(
    connection: Connection, _database_url: str, tmp_path: Path, xm_module_bytes: bytes, it_module_bytes: bytes
) -> None:
    config = _config(tmp_path, _database_url)
    (config.module_source_directory / "first.xm").write_bytes(xm_module_bytes)
    (config.module_source_directory / "second.it").write_bytes(it_module_bytes)

    summary = extract_corpus(config, workers=8).summary

    assert summary.discovered == 2
    assert len(PostgresModuleRepository(connection).list_all()) == 2


def test_a_worker_that_cannot_reach_the_catalog_reports_its_error_to_the_run(
    tmp_path: Path, xm_module_bytes: bytes, it_module_bytes: bytes
) -> None:
    """A worker's failure reaches the run that started it, beside what every other share reported."""
    config = _config(tmp_path, UNREACHABLE_DATABASE_URL)
    (config.module_source_directory / "first.xm").write_bytes(xm_module_bytes)
    (config.module_source_directory / "second.it").write_bytes(it_module_bytes)

    outcome = extract_corpus(config, workers=WORKER_COUNT)

    assert len(outcome.worker_errors) == WORKER_COUNT
    assert all(isinstance(error, OperationalError) for error in outcome.worker_errors)


def test_the_shares_that_finish_keep_their_summary_when_another_stops(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    xm_module_bytes: bytes,
    it_module_bytes: bytes,
) -> None:
    config = _config(tmp_path, _database_url)
    (config.module_source_directory / "first.xm").write_bytes(xm_module_bytes)
    (config.module_source_directory / "second.it").write_bytes(it_module_bytes)
    unreadable = config.module_source_directory / "third.mod"
    unreadable.write_bytes(b"")
    unreadable.chmod(0)

    try:
        outcome = extract_corpus(config, workers=WORKER_COUNT)
    finally:
        unreadable.chmod(0o644)

    assert outcome.worker_errors == ()
    assert [failure.path for failure in outcome.summary.failures] == [unreadable]
    assert len(outcome.summary.ingested) == 2
