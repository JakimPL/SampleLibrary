from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from sampleserver.app import create_app
from sampleserver.dependencies import get_connection, get_curation_connection


@pytest.fixture
def client(connection: Connection, _database_url: str, tmp_path: Path) -> Iterator[TestClient]:
    """A TestClient for an app whose database dependencies are overridden to the seeded connection.

    The app's own database URL is the test database, which its startup opens once to prepare the
    curation schema; every request then goes through the overridden dependencies instead.
    `library_root` is a real temporary directory, since the audio and waveform routes read actual
    files from it.

    Both the reading and the curation dependency resolve to the same connection here, which lets a
    test seed the catalog and read back what a label write did in one place. Production keeps them
    apart, and `test_app.py` is where that separation is asserted.
    """
    application = create_app(_database_url, tmp_path)

    def override_get_connection() -> Iterator[Connection]:
        yield connection

    application.dependency_overrides[get_connection] = override_get_connection
    application.dependency_overrides[get_curation_connection] = override_get_connection
    with TestClient(application) as test_client:
        yield test_client
