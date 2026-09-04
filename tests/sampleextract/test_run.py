from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from samplecore.config import LibraryConfig
from sampleextract.run import run_extraction


@pytest.fixture
def config(tmp_path: Path) -> LibraryConfig:
    source = tmp_path / "source"
    source.mkdir()
    return LibraryConfig(module_source_directory=source, library_root=tmp_path / "library")


def _write_corpus(config: LibraryConfig, *, xm_module_bytes: bytes, it_module_bytes: bytes) -> None:
    (config.module_source_directory / "song.xm").write_bytes(xm_module_bytes)
    (config.module_source_directory / "song.it").write_bytes(it_module_bytes)
    (config.module_source_directory / "corrupt.xm").write_bytes(b"not a real module file")


def test_run_extraction_ingests_valid_modules_and_reports_the_corrupt_one(
    connection: duckdb.DuckDBPyConnection, config: LibraryConfig, xm_module_bytes: bytes, it_module_bytes: bytes
) -> None:
    _write_corpus(config, xm_module_bytes=xm_module_bytes, it_module_bytes=it_module_bytes)

    summary = run_extraction(config, connection)

    assert summary.discovered == 3
    assert len(summary.ingested) == 2
    assert summary.skipped_existing == 0
    assert len(summary.failures) == 1
    assert summary.failures[0].path.name == "corrupt.xm"


def test_a_second_run_skips_every_previously_ingested_module(
    connection: duckdb.DuckDBPyConnection, config: LibraryConfig, xm_module_bytes: bytes, it_module_bytes: bytes
) -> None:
    _write_corpus(config, xm_module_bytes=xm_module_bytes, it_module_bytes=it_module_bytes)
    run_extraction(config, connection)

    summary = run_extraction(config, connection)

    assert summary.discovered == 3
    assert summary.ingested == ()
    assert summary.skipped_existing == 2
    assert len(summary.failures) == 1
