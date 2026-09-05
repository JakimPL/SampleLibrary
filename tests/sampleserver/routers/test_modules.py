from __future__ import annotations

from datetime import UTC, datetime

import duckdb
from fastapi.testclient import TestClient

from samplecore.models.module import Module
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.repositories.module import DuckDBModuleRepository


def _insert_module(connection: duckdb.DuckDBPyConnection, seed: int, *, tracker: TrackerFormat) -> Module:
    repository = DuckDBModuleRepository(connection)
    module = Module(
        hash=format(seed, "064x"),
        id=repository.next_id(),
        filename="song.xm",
        tracker=tracker,
        title="a song",
        channel_count=4,
        pattern_count=1,
        instrument_count=1,
        sample_count=1,
        file_size=1024,
        ingested_at=datetime.now(UTC),
    )
    repository.insert(module)
    return module


def test_list_modules_returns_a_page(client: TestClient, connection: duckdb.DuckDBPyConnection) -> None:
    first = _insert_module(connection, 1, tracker=TrackerFormat.XM)
    second = _insert_module(connection, 2, tracker=TrackerFormat.IT)

    response = client.get("/modules")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {item["hash"] for item in body["items"]} == {first.hash, second.hash}


def test_list_modules_respects_limit_and_offset(client: TestClient, connection: duckdb.DuckDBPyConnection) -> None:
    _insert_module(connection, 1, tracker=TrackerFormat.XM)
    _insert_module(connection, 2, tracker=TrackerFormat.XM)

    response = client.get("/modules", params={"limit": 1, "offset": 1})

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["limit"] == 1
    assert body["offset"] == 1


def test_list_modules_filters_by_tracker(client: TestClient, connection: duckdb.DuckDBPyConnection) -> None:
    xm_module = _insert_module(connection, 1, tracker=TrackerFormat.XM)
    _insert_module(connection, 2, tracker=TrackerFormat.IT)

    response = client.get("/modules", params={"tracker": "xm"})

    assert response.status_code == 200
    body = response.json()
    assert [item["hash"] for item in body["items"]] == [xm_module.hash]


def test_get_module_returns_detail_with_occurrences(client: TestClient, connection: duckdb.DuckDBPyConnection) -> None:
    module = _insert_module(connection, 1, tracker=TrackerFormat.XM)

    response = client.get(f"/modules/{module.hash}")

    assert response.status_code == 200
    body = response.json()
    assert body["hash"] == module.hash
    assert body["occurrences"] == []


def test_get_module_404s_for_an_unknown_hash(client: TestClient) -> None:
    response = client.get(f"/modules/{'f' * 64}")

    assert response.status_code == 404
