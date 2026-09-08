from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

import pytest
from sqlalchemy import Connection
from trackmod.core.songs.song import Song

from samplecore.config import LibraryConfig
from samplecore.hashing import compute_module_hash
from samplecore.models.module import Module
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.database import connect
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository
from sampleextract import run as run_module
from sampleextract.run import run_extraction


def _claim(connection: Connection, *, module_hash: str, filename: str, file_size: int) -> None:
    """Insert a bare module row, as another run reaching this same content would."""
    repository = PostgresModuleRepository(connection)
    repository.insert(
        Module(
            hash=module_hash,
            id=repository.next_id(),
            filename=filename,
            tracker=TrackerFormat.XM,
            title="a song",
            channel_count=4,
            pattern_count=1,
            instrument_count=1,
            sample_count=1,
            file_size=file_size,
            ingested_at=datetime.now(UTC),
        )
    )
    connection.commit()


@pytest.fixture
def config(tmp_path: Path) -> LibraryConfig:
    source = tmp_path / "source"
    source.mkdir()
    return LibraryConfig(module_source_directory=source, library_root=tmp_path / "library", database_url="unused")


def _write_corpus(config: LibraryConfig, *, xm_module_bytes: bytes, it_module_bytes: bytes) -> None:
    (config.module_source_directory / "song.xm").write_bytes(xm_module_bytes)
    (config.module_source_directory / "song.it").write_bytes(it_module_bytes)
    (config.module_source_directory / "corrupt.xm").write_bytes(b"not a real module file")


def test_run_extraction_ingests_valid_modules_and_reports_the_corrupt_one(
    connection: Connection, config: LibraryConfig, xm_module_bytes: bytes, it_module_bytes: bytes
) -> None:
    _write_corpus(config, xm_module_bytes=xm_module_bytes, it_module_bytes=it_module_bytes)

    summary = run_extraction(config, connection)

    assert summary.discovered == 3
    assert len(summary.ingested) == 2
    assert summary.skipped_existing == 0
    assert len(summary.failures) == 1
    assert summary.failures[0].path.name == "corrupt.xm"


def test_a_second_run_skips_every_previously_ingested_module(
    connection: Connection, config: LibraryConfig, xm_module_bytes: bytes, it_module_bytes: bytes
) -> None:
    _write_corpus(config, xm_module_bytes=xm_module_bytes, it_module_bytes=it_module_bytes)
    run_extraction(config, connection)

    summary = run_extraction(config, connection)

    assert summary.discovered == 3
    assert summary.ingested == ()
    assert summary.skipped_existing == 2
    assert len(summary.failures) == 1


def test_a_module_another_run_ingests_first_is_counted_rather_than_raised(
    connection: Connection, config: LibraryConfig, xm_module_bytes: bytes, _database_url: str
) -> None:
    """Two runs sharing one catalog can hold the same module under different names and collide.

    The second connection here stands for that other run. It claims the module in the window
    between this run finding it absent and inserting it -- a window that is otherwise a matter of
    timing -- by hooking the parse that sits inside it. Parsing and ingest are the real ones.
    """
    (config.module_source_directory / "song.xm").write_bytes(xm_module_bytes)
    module_hash = compute_module_hash(xm_module_bytes)
    real_parse = run_module.parse_module

    with connect(_database_url) as other_run:

        def parse_then_let_the_other_run_claim_it(data: bytes, *, tracker: TrackerFormat) -> Song:
            song = real_parse(data, tracker=tracker)
            _claim(other_run, module_hash=module_hash, filename="copy.xm", file_size=len(data))
            return song

        with mock.patch.object(run_module, "parse_module", parse_then_let_the_other_run_claim_it):
            summary = run_extraction(config, connection)

    assert summary.ingested == ()
    assert summary.ingested_elsewhere == 1
    assert summary.failures == ()
    assert PostgresModuleRepository(connection).get(module_hash) is not None


def test_a_collision_leaves_nothing_of_the_losing_run_behind(
    connection: Connection, config: LibraryConfig, xm_module_bytes: bytes, _database_url: str
) -> None:
    """The loser rolls its whole module back, so the catalog holds one run's work, not a blend."""
    (config.module_source_directory / "song.xm").write_bytes(xm_module_bytes)
    module_hash = compute_module_hash(xm_module_bytes)
    real_parse = run_module.parse_module

    with connect(_database_url) as other_run:

        def parse_then_let_the_other_run_claim_it(data: bytes, *, tracker: TrackerFormat) -> Song:
            song = real_parse(data, tracker=tracker)
            _claim(other_run, module_hash=module_hash, filename="copy.xm", file_size=len(data))
            return song

        with mock.patch.object(run_module, "parse_module", parse_then_let_the_other_run_claim_it):
            run_extraction(config, connection)

        stored = PostgresModuleRepository(connection).get(module_hash)

    assert stored is not None
    assert stored.filename == "copy.xm"
    assert PostgresSamplePropertiesRepository(connection).list_for_module(module_hash) == ()
