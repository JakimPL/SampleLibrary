from __future__ import annotations

import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import pytest
from fastapi.testclient import TestClient

from samplelibrary.app.asgi import create_application
from samplelibrary.app.launcher import Launcher, LibraryStatus
from samplelibrary.pipeline.settings import DescriptorSource, read_pipeline_settings

LOCAL_CLIENT: Final[tuple[str, int]] = ("127.0.0.1", 50000)
LOCAL_BASE_URL: Final[str] = "http://localhost"
IDLE_RENDERER: Final[tuple[str, ...]] = (sys.executable, "-c", "import time; time.sleep(60)")
OPENING_TIMEOUT_SECONDS: Final[float] = 30.0


@pytest.fixture
def config_path(tmp_path: Path, _database_url: str) -> Path:
    path = tmp_path / "settings" / "config.toml"
    path.parent.mkdir()
    path.write_text(
        f'[library]\nlibrary_root = "{(tmp_path / "library").as_posix()}"\ndatabase_url = "{_database_url}"\n',
        encoding="utf-8",
    )
    return path


@pytest.fixture
def unconfigured(tmp_path: Path) -> Iterator[TestClient]:
    yield from _client(tmp_path / "absent" / "config.toml")


@pytest.fixture
def configured(config_path: Path) -> Iterator[TestClient]:
    yield from _client(config_path)


def _client(config_path: Path) -> Iterator[TestClient]:
    application = create_application(
        Launcher(config_path, renderer_command=IDLE_RENDERER, pipeline_command=IDLE_RENDERER),
        frontend_directory=None,
        on_ready=lambda: None,
    )
    application.state.request_quit = lambda: None
    with TestClient(application, base_url=LOCAL_BASE_URL, client=LOCAL_CLIENT) as client:
        yield client


def _wait_until_settled(client: TestClient) -> dict[str, object]:
    deadline = time.monotonic() + OPENING_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        state: dict[str, object] = client.get("/api/setup/state").json()
        if state["status"] != LibraryStatus.STARTING:
            return state
        time.sleep(0.1)
    raise AssertionError("the library kept opening")


def test_an_application_without_a_config_file_waits_for_a_persons_choices(unconfigured: TestClient) -> None:
    state = unconfigured.get("/api/setup/state").json()

    assert state["status"] == LibraryStatus.UNCONFIGURED
    assert state["sources"] is None
    assert unconfigured.get("/api/stats").status_code == 503


def test_an_application_opens_the_library_its_config_names(configured: TestClient) -> None:
    state = _wait_until_settled(configured)

    assert state["status"] == LibraryStatus.READY
    assert state["manages_database"] is False
    assert configured.get("/api/stats").json()["sample_count"] == 0


def test_a_build_waits_for_the_library_to_open(unconfigured: TestClient) -> None:
    response = unconfigured.post("/api/setup/builds", json={"target": "catalog"})

    assert response.status_code == 409


def test_chosen_folders_are_written_and_the_library_opens_under_them(
    configured: TestClient, config_path: Path, tmp_path: Path
) -> None:
    packs = tmp_path / "packs"
    packs.mkdir()
    sources = {
        "library_root": str(tmp_path / "library"),
        "module_source_directory": None,
        "sample_directories": [str(packs)],
        "sample_exclusions": ["*loop*"],
    }

    response = configured.put("/api/setup/sources", json=sources)

    assert response.status_code == 200
    assert _wait_until_settled(configured)["status"] == LibraryStatus.READY
    assert "*loop*" in config_path.read_text(encoding="utf-8")


def test_a_library_the_application_creates_takes_the_bundled_descriptor(
    unconfigured: TestClient, tmp_path: Path
) -> None:
    packs = tmp_path / "packs"
    packs.mkdir()
    sources = {
        "library_root": str(tmp_path / "library"),
        "module_source_directory": None,
        "sample_directories": [str(packs)],
        "sample_exclusions": [],
    }

    unconfigured.put("/api/setup/sources", json=sources)

    config_path = Path(unconfigured.get("/api/setup/state").json()["config_path"])
    assert read_pipeline_settings(config_path).descriptor_source is DescriptorSource.PRETRAINED


def test_a_library_already_configured_keeps_its_pipeline_settings(
    configured: TestClient, config_path: Path, tmp_path: Path
) -> None:
    sources = {
        "library_root": str(tmp_path / "library"),
        "module_source_directory": None,
        "sample_directories": [],
        "sample_exclusions": [],
    }

    configured.put("/api/setup/sources", json={**sources, "module_source_directory": str(tmp_path)})

    assert read_pipeline_settings(config_path).descriptor_source is DescriptorSource.TRAINED


def test_folders_the_config_refuses_are_answered_with_the_reason(configured: TestClient, tmp_path: Path) -> None:
    sources = {
        "library_root": str(tmp_path / "library"),
        "module_source_directory": None,
        "sample_directories": [str(tmp_path / "packs"), str(tmp_path / "packs" / "drums")],
        "sample_exclusions": [],
    }

    response = configured.put("/api/setup/sources", json=sources)

    assert response.status_code == 422
    assert "overlap" in response.json()["detail"]


def test_the_folder_browser_lists_a_folder_and_refuses_a_missing_one(unconfigured: TestClient, tmp_path: Path) -> None:
    (tmp_path / "modules").mkdir()

    listing = unconfigured.get("/api/setup/folders", params={"path": str(tmp_path)})
    missing = unconfigured.get("/api/setup/folders", params={"path": str(tmp_path / "missing")})

    assert [folder["name"] for folder in listing.json()["folders"]] == ["modules"]
    assert missing.status_code == 404


@pytest.mark.parametrize(
    ("client_address", "base_url", "origin"),
    [
        (("192.168.1.20", 50000), LOCAL_BASE_URL, None),
        (LOCAL_CLIENT, "http://attacker.example", None),
        (LOCAL_CLIENT, LOCAL_BASE_URL, "http://attacker.example"),
    ],
)
def test_setup_answers_a_page_on_this_machine_alone(
    tmp_path: Path, client_address: tuple[str, int], base_url: str, origin: str | None
) -> None:
    application = create_application(
        Launcher(tmp_path / "config.toml", renderer_command=IDLE_RENDERER, pipeline_command=IDLE_RENDERER),
        frontend_directory=None,
        on_ready=lambda: None,
    )
    headers = {"origin": origin} if origin is not None else {}
    with TestClient(application, base_url=base_url, client=client_address) as client:
        assert client.get("/api/setup/state", headers=headers).status_code == 403
