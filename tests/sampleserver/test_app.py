from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import Connection

from sampleserver.app import create_app


def test_get_connection_opens_a_real_read_only_connection_to_the_configured_database(
    connection: Connection, _database_url: str, tmp_path: Path
) -> None:
    """Exercises `get_connection`'s real body -- opening the configured database read-only --
    rather than the dependency override every other test in this package uses. `connection` is
    depended on only for this test's isolation from others sharing the same database, not used
    directly: the schema it creates on first connect is already in place by the time this runs.
    """
    application = create_app(_database_url, tmp_path)
    with TestClient(application) as client:
        response = client.get("/stats")

    assert response.status_code == 200
    assert response.json()["module_count"] == 0
