from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from samplecore.storage.database import create_schema
from sampleserver.app import create_app
from sampleserver.dependencies import get_connection


@pytest.fixture
def connection() -> Iterator[duckdb.DuckDBPyConnection]:
    open_connection = duckdb.connect(":memory:")
    create_schema(open_connection)
    yield open_connection
    open_connection.close()


@pytest.fixture
def client(connection: duckdb.DuckDBPyConnection, tmp_path: Path) -> Iterator[TestClient]:
    """A TestClient for an app whose database dependency is overridden to the seeded connection.

    `create_app`'s own database path is never actually opened once the dependency is overridden,
    so it names no real file. `library_root` is a real temporary directory, since the audio and
    waveform routes read actual files from it.
    """
    application = create_app(Path("unused.duckdb"), tmp_path)

    def override_get_connection() -> Iterator[duckdb.DuckDBPyConnection]:
        yield connection

    application.dependency_overrides[get_connection] = override_get_connection
    with TestClient(application) as test_client:
        yield test_client
