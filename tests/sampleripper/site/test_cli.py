from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import Final

import pytest

from samplecore.config import InferenceConfig, LibraryConfig
from samplecore.exit_status import ExitStatus
from samplecore.ports import free_port
from sampleripper.children import ChildProcess
from sampleripper.site import cli as site_cli
from sampleripper.site import renderer as site_renderer
from sampleripper.site.messages import NO_AUDIO
from tests.sampleripper.site.test_admission import SiteConfig, _site_config

PROGRAM: Final[str] = "sampleripper site"
LOOPBACK: Final[str] = "127.0.0.1"
SERVING_SECONDS: Final[float] = 30.0
# A renderer that answers its status route for a moment, then ends with a status of its own.
DYING_RENDERER: Final[str] = """
import os, sys, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer

class Status(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *arguments):
        pass

server = HTTPServer(("127.0.0.1", int(sys.argv[1])), Status)
threading.Thread(target=server.serve_forever, daemon=True).start()
time.sleep(float(sys.argv[2]))
os._exit(7)
"""


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LibraryConfig:
    inference_url = f"http://{LOOPBACK}:{free_port(LOOPBACK, preferred=())}"
    site_config = _site_config(tmp_path, SiteConfig(inference_url=inference_url), monkeypatch)
    monkeypatch.setattr(site_cli, "bootstrap_cli", lambda: site_config)
    monkeypatch.setattr(site_cli, "admit_reader", lambda config: None)
    monkeypatch.setenv("PORT", "8000")
    return site_config


def _stand_in_renderer(lifetime_seconds: float) -> object:
    def build(inference: InferenceConfig, *, environment: object, config_path: Path) -> ChildProcess:
        command = (sys.executable, "-c", DYING_RENDERER, str(inference.port), str(lifetime_seconds))
        return ChildProcess("stand-in renderer", command, environment={}, log_path=None)

    return build


def test_a_site_whose_renderer_ends_while_it_serves_ends_with_a_failure(
    config: LibraryConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The platform starts a site again once it ends with a failure, and its renderer with it."""
    stopped = threading.Event()
    monkeypatch.setattr(site_cli, "site_renderer", _stand_in_renderer(lifetime_seconds=1.0))
    monkeypatch.setattr(site_cli, "stop_the_server", stopped.set)
    monkeypatch.setattr(site_cli, "run_server", lambda **options: stopped.wait(SERVING_SECONDS))

    with pytest.raises(SystemExit) as raised:
        site_cli.main([], prog=PROGRAM)

    assert raised.value.code == ExitStatus.FAILED
    assert stopped.is_set()


def test_a_site_stopping_on_its_own_stops_its_renderer_and_ends_cleanly(
    config: LibraryConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[ChildProcess] = []
    build = _stand_in_renderer(lifetime_seconds=SERVING_SECONDS)

    def recording(inference: InferenceConfig, *, environment: object, config_path: Path) -> ChildProcess:
        child = build(inference, environment=environment, config_path=config_path)  # type: ignore[operator]
        started.append(child)
        return child

    monkeypatch.setattr(site_cli, "site_renderer", recording)
    monkeypatch.setattr(site_cli, "run_server", lambda **options: None)

    site_cli.main([], prog=PROGRAM)

    assert not started[0].is_running


def test_a_site_without_its_audio_starts_and_says_so(
    config: LibraryConfig, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    (config.library_root / "objects").rmdir()
    served: list[object] = []
    monkeypatch.setattr(site_cli, "site_renderer", _stand_in_renderer(lifetime_seconds=SERVING_SECONDS))
    monkeypatch.setattr(site_cli, "run_server", lambda **options: served.append(options))

    with caplog.at_level(logging.WARNING, logger=site_cli.__name__):
        site_cli.main([], prog=PROGRAM)

    assert len(served) == 1
    assert NO_AUDIO.format(path=config.library_root / "objects") in caplog.messages


def test_a_renderer_ending_as_it_starts_fails_the_site_before_it_serves(
    config: LibraryConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    served: list[object] = []
    monkeypatch.setattr(site_cli, "site_renderer", _stand_in_renderer(lifetime_seconds=0.0))
    monkeypatch.setattr(site_renderer, "READY_SECONDS", 10.0)
    monkeypatch.setattr(site_cli, "run_server", lambda **options: served.append(options))

    with pytest.raises(SystemExit) as raised:
        site_cli.main([], prog=PROGRAM)

    assert raised.value.code == ExitStatus.FAILED
    assert served == []


def test_a_refused_site_starts_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    site_config = _site_config(tmp_path, SiteConfig(exposure="local"), monkeypatch)
    monkeypatch.setattr(site_cli, "bootstrap_cli", lambda: site_config)
    monkeypatch.setenv("PORT", "8000")
    monkeypatch.setattr(site_cli, "site_renderer", lambda *arguments, **options: pytest.fail("a renderer started"))

    with pytest.raises(SystemExit) as raised:
        site_cli.main([], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED


def test_the_renderer_holds_no_database_connection_and_computes_on_one_thread(tmp_path: Path) -> None:
    environment = {
        "SAMPLERIPPER_SERVER_DATABASE_URL": "postgresql+psycopg://reader:x@db/site",
        "SAMPLERIPPER_PUBLISH_READER_PASSWORD": "x",
        "PATH": "/usr/bin",
    }

    child = site_renderer.site_renderer(
        InferenceConfig(url="http://127.0.0.1:8010"), environment=environment, config_path=tmp_path / "config.toml"
    )

    handed = child.environment
    assert not any(name in handed for name in site_renderer.DATABASE_VARIABLES)
    assert handed["PATH"] == "/usr/bin"
    assert handed["OPENBLAS_NUM_THREADS"] == "1"
