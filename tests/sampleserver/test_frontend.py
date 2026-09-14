from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from sampleserver.app import API_PREFIX, create_app
from sampleserver.frontend import INDEX_DOCUMENT
from tests.sampleserver.conftest import INFERENCE_URL

INDEX_MARKUP = "<!doctype html><title>SampleLibrary</title>"
SCRIPT_BODY = "console.log('sample library');"


@pytest.fixture
def frontend_directory(tmp_path: Path) -> Path:
    directory = tmp_path / "dist"
    (directory / "assets").mkdir(parents=True)
    (directory / INDEX_DOCUMENT).write_text(INDEX_MARKUP, encoding="utf-8")
    (directory / "assets" / "index.js").write_text(SCRIPT_BODY, encoding="utf-8")
    return directory


@pytest.fixture
def served(
    connection: Connection, _database_url: str, tmp_path: Path, frontend_directory: Path
) -> Iterator[TestClient]:
    application = create_app(_database_url, tmp_path, INFERENCE_URL, frontend_directory=frontend_directory)
    with TestClient(application) as client:
        yield client


@pytest.mark.parametrize("path", ["/", "/samples/0123abcd", "/modules/0123abcd/instruments"])
def test_a_page_path_answers_with_the_application(served: TestClient, path: str) -> None:
    response = served.get(path)

    assert response.status_code == 200
    assert response.text == INDEX_MARKUP


def test_a_built_file_is_served_as_itself(served: TestClient) -> None:
    response = served.get("/assets/index.js")

    assert response.status_code == 200
    assert response.text == SCRIPT_BODY


@pytest.mark.parametrize("path", ["/assets/index-stale.js", "/favicon.ico"])
def test_a_missing_file_is_a_plain_miss(served: TestClient, path: str) -> None:
    assert served.get(path).status_code == 404


def test_the_api_keeps_its_own_routes_and_misses(served: TestClient) -> None:
    assert served.get(f"{API_PREFIX}/stats").json()["module_count"] == 0

    missing = served.get(f"{API_PREFIX}/no-such-route")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Not Found"}


def test_an_app_built_without_a_frontend_serves_the_api_alone(
    connection: Connection, _database_url: str, tmp_path: Path
) -> None:
    with TestClient(create_app(_database_url, tmp_path, INFERENCE_URL, frontend_directory=None)) as client:
        assert client.get("/").status_code == 404
        assert client.get(f"{API_PREFIX}/stats").status_code == 200


def test_the_api_answers_a_wrong_method_and_a_trailing_slash_as_it_does_alone(served: TestClient) -> None:
    """A frontend at the root takes no path under the API, so the API's own answers stand."""
    wrong_method = served.post(f"{API_PREFIX}/stats")
    trailing_slash = served.get(f"{API_PREFIX}/samples/", follow_redirects=False)

    assert wrong_method.status_code == 405
    assert wrong_method.headers["allow"] == "GET"
    assert trailing_slash.status_code == 307
    assert trailing_slash.headers["location"].endswith(f"{API_PREFIX}/samples")
