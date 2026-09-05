from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from samplecore.storage.database import connect
from sampleserver.app import create_app


def test_get_connection_opens_a_real_read_only_connection_to_the_configured_database(tmp_path: Path) -> None:
    """Exercises `get_connection`'s real body -- opening the configured file read-only and closing
    it afterward -- rather than the dependency override every other test in this package uses.
    """
    database_path = tmp_path / "test.duckdb"
    connect(database_path).close()

    application = create_app(database_path)
    with TestClient(application) as client:
        response = client.get("/stats")

    assert response.status_code == 200
    assert response.json()["module_count"] == 0
