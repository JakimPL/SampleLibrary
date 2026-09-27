from __future__ import annotations

from pathlib import Path
from typing import Final

from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from samplecore.models.service_role import ServiceRole
from samplecore.storage.curation import CURATION_SCHEMA
from sampleserver.app import API_PREFIX, create_app
from tests.sampleserver.conftest import INFERENCE_URL, LOCAL_CLIENT, LOCAL_ORIGIN, LOCAL_SERVER

UNUSED_DATABASE_URL: Final[str] = "postgresql+psycopg://unused/unused"
READING_METHODS: Final[frozenset[str]] = frozenset({"GET", "HEAD"})


def test_get_connection_opens_a_real_read_only_connection_to_the_configured_database(
    connection: Connection, _database_url: str, tmp_path: Path
) -> None:
    """Exercises `get_connection`'s real body -- opening the configured database read-only --
    rather than the dependency override every other test in this package uses. `connection` is
    depended on only for this test's isolation from others sharing the same database, not used
    directly: the schema it creates on first connect is already in place by the time this runs.
    """
    application = create_app(
        _database_url,
        tmp_path,
        INFERENCE_URL,
        role=ServiceRole.READER,
        server=LOCAL_SERVER,
        sample_directories=(),
        frontend_directory=None,
    )
    with TestClient(application, base_url=LOCAL_ORIGIN, client=LOCAL_CLIENT) as client:
        response = client.get(f"{API_PREFIX}/stats")

    assert response.status_code == 200
    assert response.json()["module_count"] == 0


def test_a_response_past_a_kilobyte_goes_out_gzipped_when_the_caller_accepts_it(
    connection: Connection, _database_url: str, tmp_path: Path
) -> None:
    """The cloud's payload is text that compresses several-fold, and every route shares the middleware."""
    with TestClient(
        create_app(
            _database_url,
            tmp_path,
            INFERENCE_URL,
            role=ServiceRole.READER,
            server=LOCAL_SERVER,
            sample_directories=(),
            frontend_directory=None,
        ),
        base_url=LOCAL_ORIGIN,
        client=LOCAL_CLIENT,
    ) as client:
        response = client.get(f"{API_PREFIX}/openapi.json", headers={"Accept-Encoding": "gzip"})

    assert response.headers["content-encoding"] == "gzip"
    assert "paths" in response.json()


def test_every_route_is_served_under_the_api_prefix(connection: Connection, _database_url: str, tmp_path: Path) -> None:
    """The API occupies one path segment of its own, leaving `/samples/{hash}` to the frontend.

    A single-page application routes `/samples/{hash}` in the browser, so a dev server forwarding
    that path to this API would answer a reload with JSON instead of the dashboard. Holding the
    whole API under one prefix is what keeps the two apart, which makes it worth pinning here
    rather than leaving it to the paths the other tests happen to name.
    """
    served = set(
        create_app(
            _database_url,
            tmp_path,
            INFERENCE_URL,
            role=ServiceRole.CURATOR,
            server=LOCAL_SERVER,
            sample_directories=(),
            frontend_directory=None,
        ).openapi()["paths"]
    )

    assert f"{API_PREFIX}/samples" in served
    assert f"{API_PREFIX}/curation/annotations/{{sample_hash}}" in served
    assert f"{API_PREFIX}/morph/audio" in served
    assert all(path.startswith(f"{API_PREFIX}/") for path in served)


def _writing_routes(role: ServiceRole, tmp_path: Path) -> set[tuple[str, str]]:
    application = create_app(
        UNUSED_DATABASE_URL,
        tmp_path,
        INFERENCE_URL,
        role=role,
        server=LOCAL_SERVER,
        sample_directories=(),
        frontend_directory=None,
    )
    return {
        (method.upper(), path)
        for path, operations in application.openapi()["paths"].items()
        for method in operations
        if method.upper() not in READING_METHODS
    }


def test_a_reader_serves_no_route_that_writes(tmp_path: Path) -> None:
    assert _writing_routes(ServiceRole.READER, tmp_path) == set()


def test_a_curator_writes_labels_alone(tmp_path: Path) -> None:
    assert _writing_routes(ServiceRole.CURATOR, tmp_path) == {
        ("PATCH", f"{API_PREFIX}/curation/annotations/{{sample_hash}}")
    }


def test_a_reader_refuses_a_label_change_and_says_so(client: TestClient) -> None:
    response = client.patch(f"/curation/annotations/{'a' * 64}", json={"scope": "sample", "rating": 3})

    assert response.status_code in (404, 405)
    assert client.get("/curation/access").json() == {"label_editing": False, "curation_shown": True}
