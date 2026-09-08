from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from samplecore.storage.curation import CURATION_SCHEMA
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


def test_starting_the_app_prepares_the_curation_schema_a_listing_reads_through(
    connection: Connection, _database_url: str, tmp_path: Path
) -> None:
    """A catalog the offline pipelines have never written to still has to serve a listing.

    The listing reads a sample's hand annotation as part of its own query, and the read-only
    connection every route uses can create nothing, so startup is the only place this can happen.
    """
    connection.execute(text(f"DROP SCHEMA IF EXISTS {CURATION_SCHEMA} CASCADE"))
    connection.commit()

    with TestClient(create_app(_database_url, tmp_path)) as client:
        assert client.get("/samples").status_code == 200

    schema = connection.execute(
        text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = :name"),
        {"name": CURATION_SCHEMA},
    ).fetchone()
    assert schema is not None
