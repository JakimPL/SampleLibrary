from __future__ import annotations

import socket
import sys
import time
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from samplecore.config import DEFAULT_SERVER_CONFIG, PIPELINE_TABLE, load_config
from samplelibrary.app.asgi import create_application
from samplelibrary.app.installation import Installation, this_installation
from samplelibrary.app.launcher import PUBLIC_LIBRARY_REFUSED, Launcher, LibraryStatus
from samplelibrary.app.listener import CLOSED_TO_THE_NETWORK, HomeNetworkReach, starting_policy
from samplelibrary.pipeline.settings import DescriptorSource, read_pipeline_settings
from sampleserver.policy import ServingPolicy
from tests.sampleserver.conftest import SITE_VISITORS_TABLE

LOCAL_CLIENT: Final[tuple[str, int]] = ("127.0.0.1", 50000)
LOCAL_BASE_URL: Final[str] = "http://localhost"
IDLE_RENDERER: Final[tuple[str, ...]] = (sys.executable, "-c", "import time; time.sleep(60)")
TEST_CARD: Final[str] = "Test Card"
REPORTED_DEVICE: Final[tuple[str, ...]] = (sys.executable, "-c", f'print(\'{{"card": "{TEST_CARD}"}}\')')
SILENT_DEVICE: Final[tuple[str, ...]] = (sys.executable, "-c", "raise SystemExit(1)")
OPENING_TIMEOUT_SECONDS: Final[float] = 30.0
LOCAL_POLICY: Final[ServingPolicy] = ServingPolicy.of(DEFAULT_SERVER_CONFIG)
HOME_DEVICE: Final[tuple[str, int]] = ("192.168.1.20", 50000)
HOME_BASE_URL: Final[str] = "http://192.168.1.10"
HOME_REACH: Final[HomeNetworkReach] = HomeNetworkReach(open=True, address=f"{HOME_BASE_URL}:27440/")
NETWORK_SERVER_TABLE: Final[str] = '[server]\nexposure = "network"\n'


@pytest.fixture
def config_path(tmp_path: Path, worker_cluster_port: None) -> Path:
    """A config naming a library that keeps its own database, the way the SampleLibrary app creates one."""
    path = tmp_path / "settings" / "config.toml"
    path.parent.mkdir()
    path.write_text(f'[library]\nlibrary_root = "{(tmp_path / "library").as_posix()}"\n', encoding="utf-8")
    return path


@pytest.fixture
def unconfigured(tmp_path: Path) -> Iterator[TestClient]:
    yield from _client(tmp_path / "absent" / "config.toml", device_command=REPORTED_DEVICE)


@pytest.fixture
def configured(config_path: Path) -> Iterator[TestClient]:
    yield from _client(config_path, device_command=REPORTED_DEVICE)


def _client(config_path: Path, *, device_command: tuple[str, ...]) -> Iterator[TestClient]:
    application = create_application(
        Launcher(
            config_path,
            renderer_command=IDLE_RENDERER,
            pipeline_command=IDLE_RENDERER,
            device_command=device_command,
            home_network=CLOSED_TO_THE_NETWORK,
        ),
        frontend_directory=None,
        on_ready=lambda: None,
        policy=LOCAL_POLICY,
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
    assert state["manages_database"] is True
    assert configured.get("/api/stats").json()["sample_count"] == 0


def test_the_application_names_its_installation(unconfigured: TestClient) -> None:
    answer = unconfigured.get("/api/setup/installation").json()

    assert Installation.model_validate(answer) == this_installation()


def test_quitting_closes_the_library_before_the_server_stops(config_path: Path) -> None:
    launcher = Launcher(
        config_path,
        renderer_command=IDLE_RENDERER,
        pipeline_command=IDLE_RENDERER,
        device_command=REPORTED_DEVICE,
        home_network=CLOSED_TO_THE_NETWORK,
    )
    application = create_application(launcher, frontend_directory=None, on_ready=lambda: None, policy=LOCAL_POLICY)
    library_open_at_quit: list[bool] = []
    application.state.request_quit = lambda: library_open_at_quit.append(launcher.catalog is not None)
    with TestClient(application, base_url=LOCAL_BASE_URL, client=LOCAL_CLIENT) as client:
        assert _wait_until_settled(client)["status"] == LibraryStatus.READY

        assert client.post("/api/setup/quit").status_code == 202

    assert library_open_at_quit == [False]


def test_a_renderer_whose_port_is_taken_listens_on_another_one(config_path: Path, tmp_path: Path) -> None:
    arguments_path = tmp_path / "renderer-arguments.txt"
    recording_renderer = (
        sys.executable,
        "-c",
        "import pathlib, sys, time; pathlib.Path(sys.argv[1]).write_text(' '.join(sys.argv[2:])); time.sleep(60)",
        str(arguments_path),
    )
    with socket.create_server(("127.0.0.1", 0)) as holder:
        taken_port: int = holder.getsockname()[1]
        with config_path.open("a", encoding="utf-8") as config:
            config.write(f'\n[inference]\nurl = "http://127.0.0.1:{taken_port}"\n')
        launcher = Launcher(
            config_path,
            renderer_command=recording_renderer,
            pipeline_command=IDLE_RENDERER,
            device_command=REPORTED_DEVICE,
            home_network=CLOSED_TO_THE_NETWORK,
        )
        application = create_application(launcher, frontend_directory=None, on_ready=lambda: None, policy=LOCAL_POLICY)
        application.state.request_quit = lambda: None
        with TestClient(application, base_url=LOCAL_BASE_URL, client=LOCAL_CLIENT) as client:
            assert _wait_until_settled(client)["status"] == LibraryStatus.READY
            assert launcher.catalog is not None
            renderer_url = urlsplit(launcher.catalog.state.inference_url)
            deadline = time.monotonic() + OPENING_TIMEOUT_SECONDS
            while not arguments_path.is_file() and time.monotonic() < deadline:
                time.sleep(0.1)

    assert renderer_url.port not in (None, taken_port)
    assert arguments_path.read_text(encoding="utf-8") == f"--host 127.0.0.1 --port {renderer_url.port}"


def test_a_library_another_application_holds_open_stays_with_it(config_path: Path) -> None:
    for first in _client(config_path, device_command=REPORTED_DEVICE):
        assert _wait_until_settled(first)["status"] == LibraryStatus.READY
        for second in _client(config_path, device_command=REPORTED_DEVICE):
            state = _wait_until_settled(second)

            assert state["status"] == LibraryStatus.FAILED
            assert state["problem"] == "Another SampleLibrary has this library open. Quit that one, then try again."
        assert first.get("/api/stats").status_code == 200


def test_a_library_whose_curator_may_do_more_than_record_labels_stays_closed(
    tmp_path: Path, _database_url: str
) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        f'[library]\nlibrary_root = "{(tmp_path / "library").as_posix()}"\n'
        f'database_url = "{_database_url}"\ncuration_database_url = "{_database_url}"\n',
        encoding="utf-8",
    )
    for client in _client(path, device_command=REPORTED_DEVICE):
        state = _wait_until_settled(client)

        assert state["status"] == LibraryStatus.FAILED
        assert "doesn't fit a curator" in str(state["problem"])
        assert client.get("/api/stats").status_code == 503


def test_a_library_served_to_anyone_stays_closed_in_the_application(tmp_path: Path) -> None:
    """The application edits labels and writes its config, which a library served to anyone offers no one."""
    path = tmp_path / "config.toml"
    path.write_text(
        f'[library]\nlibrary_root = "{(tmp_path / "library").as_posix()}"\n[server]\nexposure = "public"\n'
        f"{SITE_VISITORS_TABLE}",
        encoding="utf-8",
    )
    for client in _client(path, device_command=REPORTED_DEVICE):
        state = _wait_until_settled(client)

        assert state["status"] == LibraryStatus.FAILED
        assert state["problem"] == PUBLIC_LIBRARY_REFUSED
        assert client.get("/api/stats").status_code == 503


def _build_device(client: TestClient) -> dict[str, object]:
    deadline = time.monotonic() + OPENING_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        device: dict[str, object] | None = client.get("/api/setup/state").json()["build_device"]
        if device is not None:
            return device
        time.sleep(0.1)
    raise AssertionError("the application never named the device builds use")


def test_the_application_names_the_card_builds_compute_on(unconfigured: TestClient) -> None:
    assert _build_device(unconfigured) == {"card": TEST_CARD}


def test_a_device_the_application_cannot_ask_about_leaves_builds_on_the_processor(tmp_path: Path) -> None:
    for client in _client(tmp_path / "config.toml", device_command=SILENT_DEVICE):
        assert _build_device(client) == {"card": None}


def test_the_options_are_written_for_the_next_build_and_start(configured: TestClient, config_path: Path) -> None:
    _wait_until_settled(configured)

    response = configured.put("/api/setup/options", json={"build_cloud": False, "open_to_network": True})

    assert response.json()["options"] == {"build_cloud": False, "open_to_network": True}
    assert response.json()["home_network"] == {"open": False, "address": None}
    assert not load_config(config_path).build_cloud
    assert load_config(config_path).server.answers_the_home_network


def test_the_options_wait_for_the_folders(unconfigured: TestClient) -> None:
    response = unconfigured.put("/api/setup/options", json={"build_cloud": False, "open_to_network": False})

    assert response.status_code == 409


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


def test_a_library_the_application_creates_leaves_its_descriptor_to_the_automatic_choice(
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
    assert PIPELINE_TABLE not in tomllib.loads(config_path.read_text(encoding="utf-8"))


def test_a_library_already_configured_keeps_its_pipeline_settings(
    configured: TestClient, config_path: Path, tmp_path: Path
) -> None:
    sources = {
        "library_root": str(tmp_path / "library"),
        "module_source_directory": None,
        "sample_directories": [],
        "sample_exclusions": [],
    }

    config_path.write_text(
        f'{config_path.read_text(encoding="utf-8")}\n[{PIPELINE_TABLE}]\ndescriptor_source = "trained"\nworkers = 4\n',
        encoding="utf-8",
    )

    configured.put("/api/setup/sources", json={**sources, "module_source_directory": str(tmp_path)})

    settings = read_pipeline_settings(config_path)
    assert (settings.descriptor_source, settings.workers) == (DescriptorSource.TRAINED, 4)


def test_folders_stay_as_they_are_while_a_build_runs(configured: TestClient, config_path: Path, tmp_path: Path) -> None:
    _wait_until_settled(configured)
    written = config_path.read_text(encoding="utf-8")
    sources = {
        "library_root": str(tmp_path / "elsewhere"),
        "module_source_directory": str(tmp_path),
        "sample_directories": [],
        "sample_exclusions": [],
    }

    build = configured.post("/api/setup/builds", json={"target": "catalog"})
    response = configured.put("/api/setup/sources", json=sources)

    assert build.status_code == 202
    assert response.status_code == 409
    assert config_path.read_text(encoding="utf-8") == written


def test_folders_the_config_refuses_are_answered_with_the_reason(configured: TestClient, tmp_path: Path) -> None:
    sources = {
        "library_root": str(tmp_path / "library"),
        "module_source_directory": None,
        "sample_directories": [str(tmp_path / "packs"), str(tmp_path / "packs" / "drums")],
        "sample_exclusions": [],
    }

    response = configured.put("/api/setup/sources", json=sources)

    assert response.status_code == 422
    assert response.json()["detail"] == (
        f"{tmp_path / 'packs'} and {tmp_path / 'packs' / 'drums'} overlap. Choose each folder only once."
    )


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
        Launcher(
            tmp_path / "config.toml",
            renderer_command=IDLE_RENDERER,
            pipeline_command=IDLE_RENDERER,
            device_command=REPORTED_DEVICE,
            home_network=CLOSED_TO_THE_NETWORK,
        ),
        frontend_directory=None,
        on_ready=lambda: None,
        policy=LOCAL_POLICY,
    )
    headers = {"origin": origin} if origin is not None else {}
    with TestClient(application, base_url=base_url, client=client_address) as client:
        assert client.get("/api/setup/state", headers=headers).status_code == 403
        assert client.get("/api/stats", headers=headers).status_code == 403


def test_a_name_rebound_to_this_computer_reaches_nothing(unconfigured: TestClient, tmp_path: Path) -> None:
    """A page whose name a URL parser rejects, pointed at this computer, still names itself in its Host header."""
    rebound = {"host": "a_b.attacker.example:27440"}

    assert unconfigured.get("/api/setup/folders", params={"path": str(tmp_path)}, headers=rebound).status_code == 403
    assert unconfigured.get("/api/setup/state", headers=rebound).status_code == 403
    assert unconfigured.get("/api/stats", headers=rebound).status_code == 403


def test_the_application_refuses_a_request_a_proxy_forwarded(unconfigured: TestClient) -> None:
    assert unconfigured.get("/api/setup/state", headers={"x-forwarded-for": "203.0.113.9"}).status_code == 403


@pytest.fixture
def home_network_application(config_path: Path) -> Iterator[FastAPI]:
    """The application opened to the home network, as its config says, holding its library open."""
    with config_path.open("a", encoding="utf-8") as config:
        config.write(NETWORK_SERVER_TABLE)
    policy = starting_policy(config_path)
    application = create_application(
        Launcher(
            config_path,
            renderer_command=IDLE_RENDERER,
            pipeline_command=IDLE_RENDERER,
            device_command=REPORTED_DEVICE,
            home_network=HOME_REACH,
        ),
        frontend_directory=None,
        on_ready=lambda: None,
        policy=policy,
    )
    application.state.request_quit = lambda: None
    with TestClient(application, base_url=LOCAL_BASE_URL, client=LOCAL_CLIENT) as client:
        assert _wait_until_settled(client)["home_network"] == HOME_REACH.model_dump()
        yield application


def test_a_device_on_the_home_network_reads_the_library(home_network_application: FastAPI) -> None:
    device = TestClient(home_network_application, base_url=HOME_BASE_URL, client=HOME_DEVICE)

    assert device.get("/api/stats").status_code == 200
    assert device.get("/api/curation/access").json()["label_editing"] is False


def test_a_device_on_the_home_network_changes_nothing(home_network_application: FastAPI) -> None:
    device = TestClient(home_network_application, base_url=HOME_BASE_URL, client=HOME_DEVICE)

    assert device.get("/api/setup/state").status_code == 403
    assert device.put("/api/setup/options", json={"build_cloud": True, "open_to_network": True}).status_code == 403
    assert device.post("/api/setup/quit").status_code == 403
    assert device.patch(f"/api/curation/annotations/{'0' * 64}", json={"rating": 5}).status_code == 403


@pytest.mark.parametrize(
    ("client_address", "base_url", "origin"),
    [
        (("203.0.113.9", 50000), HOME_BASE_URL, None),
        (("198.18.0.1", 50000), HOME_BASE_URL, None),
        (HOME_DEVICE, "http://rebound.example", None),
        (HOME_DEVICE, HOME_BASE_URL, "http://attacker.example"),
        (LOCAL_CLIENT, LOCAL_BASE_URL, "http://attacker.example"),
    ],
    ids=["a public address", "the benchmarking range", "a rebound name", "a page elsewhere", "a page here elsewhere"],
)
def test_the_home_network_opens_to_its_own_devices_alone(
    home_network_application: FastAPI, client_address: tuple[str, int], base_url: str, origin: str | None
) -> None:
    headers = {"origin": origin} if origin is not None else {}
    stranger = TestClient(home_network_application, base_url=base_url, client=client_address)

    assert stranger.get("/api/stats", headers=headers).status_code == 403


def test_a_library_opened_to_the_network_meanwhile_opens_at_the_next_start(
    configured: TestClient, config_path: Path
) -> None:
    _wait_until_settled(configured)
    configured.put("/api/setup/options", json={"build_cloud": True, "open_to_network": True})
    device = TestClient(configured.app, base_url=HOME_BASE_URL, client=HOME_DEVICE)

    assert device.get("/api/stats").status_code == 403
    assert starting_policy(config_path).listens_beyond_this_computer
