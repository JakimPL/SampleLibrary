from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Connection, event, text
from starlette.types import Message, Receive, Scope, Send

from samplecore.models.service_role import ServiceRole
from samplecore.storage.database import (
    SERVED_IDLE_TRANSACTION_MILLISECONDS,
    SERVED_STATEMENT_TIMEOUT_MILLISECONDS,
    create_pooled_engine,
)
from sampleserver.app import API_PREFIX, create_app
from sampleserver.headers import EVERY_RESPONSE_HEADERS, PAGE_CONTENT_SECURITY_POLICY, STRICT_TRANSPORT_SECURITY
from tests.sampleserver.conftest import INFERENCE_URL, LOCAL_CLIENT, LOCAL_ORIGIN, LOCAL_SERVER

INDEX_MARKUP: Final[str] = "<!doctype html><title>SampleRipper</title>"
MILLISECONDS_PER_SECOND: Final[int] = 1000
SECONDS_PER_MINUTE: Final[int] = 60


class ConnectionsAtResponseStart:
    """Middleware noting how many pooled connections are out at the moment each response begins."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app
        self.checked_out: list[int] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def noting(message: Message) -> None:
            if message["type"] == "http.response.start":
                self.checked_out.append(self._app.state.engine.pool.checkedout())
            await send(message)

        await self._app(scope, receive, noting)


@pytest.fixture
def served_app(connection: Connection, _database_url: str, tmp_path: Path) -> FastAPI:
    """An app reading the test catalog through its own pool, as a served one does."""
    return create_app(
        _database_url,
        tmp_path,
        INFERENCE_URL,
        role=ServiceRole.READER,
        server=LOCAL_SERVER,
        sample_directories=(),
        frontend_directory=None,
    )


@pytest.fixture
def frontend_directory(tmp_path: Path) -> Path:
    directory = tmp_path / "dist"
    directory.mkdir()
    (directory / "index.html").write_text(INDEX_MARKUP, encoding="utf-8")
    return directory


@pytest.fixture
def served_pages(
    connection: Connection, _database_url: str, tmp_path: Path, frontend_directory: Path
) -> Iterator[TestClient]:
    application = create_app(
        _database_url,
        tmp_path,
        INFERENCE_URL,
        role=ServiceRole.READER,
        server=LOCAL_SERVER,
        sample_directories=(),
        frontend_directory=frontend_directory,
    )
    with TestClient(application, base_url=LOCAL_ORIGIN, client=LOCAL_CLIENT) as client:
        yield client


@pytest.mark.parametrize("path", ["/", "/samples/0123abcd", f"{API_PREFIX}/stats", f"{API_PREFIX}/no-such-route"])
def test_every_response_is_read_as_its_type_framed_by_no_page_and_named_to_no_other_site(
    served_pages: TestClient, path: str
) -> None:
    headers = served_pages.get(path).headers

    assert {name: headers.get(name) for name in EVERY_RESPONSE_HEADERS} == EVERY_RESPONSE_HEADERS


def test_a_page_of_the_application_carries_its_content_security_policy(served_pages: TestClient) -> None:
    assert served_pages.get("/samples/0123abcd").headers["content-security-policy"] == PAGE_CONTENT_SECURITY_POLICY
    assert served_pages.get(f"{API_PREFIX}x").headers["content-security-policy"] == PAGE_CONTENT_SECURITY_POLICY
    assert "content-security-policy" not in served_pages.get(f"{API_PREFIX}/stats").headers


def test_browsers_are_told_to_reach_a_site_over_https_alone(public_client: TestClient, client: TestClient) -> None:
    assert public_client.get("/stats").headers["strict-transport-security"] == STRICT_TRANSPORT_SECURITY
    assert "strict-transport-security" not in client.get("/stats").headers


def test_the_health_check_reads_that_the_catalog_answers(client: TestClient) -> None:
    assert client.get("/health").json() == {"catalog_answers": True}


def test_the_pool_has_its_connection_back_before_an_answer_goes_out(served_app: FastAPI) -> None:
    """A caller reading an answer slowly holds none of the pool while it reads."""
    noting = ConnectionsAtResponseStart(served_app)
    with TestClient(noting, base_url=LOCAL_ORIGIN, client=LOCAL_CLIENT) as client:
        for path in ("/samples", "/stats", "/cloud", "/modules"):
            client.get(f"{API_PREFIX}{path}")

    assert noting.checked_out == [0, 0, 0, 0]


def test_a_request_reads_the_catalog_through_one_connection(served_app: FastAPI) -> None:
    """The listing's route and the dependency naming the shown scoring share the route's connection."""
    with TestClient(served_app, base_url=LOCAL_ORIGIN, client=LOCAL_CLIENT) as client:
        checkouts: list[object] = []
        event.listen(served_app.state.engine, "checkout", lambda *arguments: checkouts.append(arguments))
        client.get(f"{API_PREFIX}/samples")

    assert len(checkouts) == 1


def test_a_served_connection_ends_a_long_statement_and_an_idle_transaction(_database_url: str) -> None:
    engine = create_pooled_engine(_database_url, pool_size=1)
    try:
        with engine.connect() as connection:
            statement = connection.execute(text("SHOW statement_timeout")).scalar_one()
            idle = connection.execute(text("SHOW idle_in_transaction_session_timeout")).scalar_one()
    finally:
        engine.dispose()

    assert statement == f"{SERVED_STATEMENT_TIMEOUT_MILLISECONDS // MILLISECONDS_PER_SECOND}s"
    assert idle == f"{SERVED_IDLE_TRANSACTION_MILLISECONDS // MILLISECONDS_PER_SECOND // SECONDS_PER_MINUTE}min"
