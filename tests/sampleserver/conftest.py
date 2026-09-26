from __future__ import annotations

from collections.abc import Iterator
from contextlib import nullcontext
from pathlib import Path
from typing import Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from samplecore.storage.service_roles import ServiceRole
from sampleserver.app import API_PREFIX, create_app
from sampleserver.dependencies import get_connection, get_connection_opener, get_curation_connection

INFERENCE_URL = "http://inference.test"


LOCAL_CLIENT: Final[tuple[str, int]] = ("127.0.0.1", 50000)
LOCAL_BASE_URL: Final[str] = f"http://localhost{API_PREFIX}"


@pytest.fixture
def client(connection: Connection, _database_url: str, tmp_path: Path) -> Iterator[TestClient]:
    """A TestClient for a reader's app, as a deployed site serves it, over the seeded connection.

    The app's own database URL is the test database, which its startup opens once to prepare the
    curation schema; every request then goes through the overridden dependencies instead.
    `library_root` is a real temporary directory, since the audio and waveform routes read actual
    files from it.

    The base URL carries `API_PREFIX`, so a test names a route the way the router declares it and
    the client resolves it to where the app actually serves it. `test_app.py` pins the prefix
    itself, against a client built without one.
    """
    application = _seeded_app(connection, _database_url, tmp_path, role=ServiceRole.READER)
    with TestClient(application, base_url=f"http://testserver{API_PREFIX}") as test_client:
        yield test_client


@pytest.fixture
def curating_client(connection: Connection, _database_url: str, tmp_path: Path) -> Iterator[TestClient]:
    """A TestClient for a curator's app, as the application on a person's own computer serves it, asked from there.

    Both the reading and the curation dependency resolve to the seeded connection, which lets a
    test seed the catalog and read back what a label write did in one place. Production keeps them
    apart, and `test_app.py` is where that separation is asserted.
    """
    application = _seeded_app(connection, _database_url, tmp_path, role=ServiceRole.CURATOR)
    with TestClient(application, base_url=LOCAL_BASE_URL, client=LOCAL_CLIENT) as test_client:
        yield test_client


def _seeded_app(connection: Connection, database_url: str, library_root: Path, *, role: ServiceRole) -> FastAPI:
    application = create_app(database_url, library_root, INFERENCE_URL, role=role, frontend_directory=None)

    def override_get_connection() -> Iterator[Connection]:
        yield connection

    application.dependency_overrides[get_connection] = override_get_connection
    application.dependency_overrides[get_connection_opener] = lambda: lambda: nullcontext(connection)
    application.dependency_overrides[get_curation_connection] = override_get_connection
    return application
