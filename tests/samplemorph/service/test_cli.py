from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE, InferenceConfig
from samplecore.exit_status import ExitStatus
from samplemorph.cli import MorphCommand, main
from samplemorph.routes.selection import DEFAULT_SELECTION_PATH, read_route_selection
from samplemorph.service import renderer as renderer_module
from samplemorph.service.renderer import load_renderer
from samplemorph.service.settings import ServiceSettings

PROGRAM = "samplelibrary morph"
CONFIGURED_HOST = "0.0.0.0"
CONFIGURED_PORT = 9010
OVERRIDING_PORT = 9100


@dataclass
class RecordedRun:
    application: FastAPI | None = None
    host: str | None = None
    port: int | None = None


def _write_config(tmp_path: Path, *, inference_url: str | None) -> Path:
    config_path = tmp_path / "config.toml"
    inference = f'[inference]\nurl = "{inference_url}"\n' if inference_url is not None else ""
    config_path.write_text(
        f'[library]\nmodule_source_directory = "{tmp_path.as_posix()}"\nlibrary_root = "{tmp_path.as_posix()}"\n'
        f'database_url = "postgresql+psycopg://user:pass@host/db"\n{inference}',
        encoding="utf-8",
    )
    return config_path


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch, settings: ServiceSettings) -> RecordedRun:
    """Captures what the serve command hands uvicorn, in place of binding a socket, over a renderer loaded once."""
    run = RecordedRun()
    renderer = load_renderer(settings)

    def record(application: FastAPI, *, host: str, port: int) -> None:
        run.application = application
        run.host = host
        run.port = port

    monkeypatch.setattr(uvicorn, "run", record)
    monkeypatch.setattr(renderer_module, "load_renderer", lambda loaded_settings: renderer)
    return run


def test_the_process_binds_the_address_the_configuration_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, recorded: RecordedRun
) -> None:
    config_path = _write_config(tmp_path, inference_url=f"http://{CONFIGURED_HOST}:{CONFIGURED_PORT}")
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))

    main([MorphCommand.SERVE], prog=PROGRAM)

    assert (recorded.host, recorded.port) == (CONFIGURED_HOST, CONFIGURED_PORT)
    assert recorded.application is not None
    assert recorded.application.state.renderer.status().name.startswith("envelope")


def test_a_flag_overrides_the_configured_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, recorded: RecordedRun
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, inference_url=None)))

    main([MorphCommand.SERVE, "--port", str(OVERRIDING_PORT)], prog=PROGRAM)

    assert recorded.host == InferenceConfig().host
    assert recorded.port == OVERRIDING_PORT


def test_a_selection_file_the_process_cannot_read_ends_it_with_one_message_before_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bound: list[str] = []
    monkeypatch.setattr(uvicorn, "run", lambda *arguments, **options: bound.append("bound"))
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, inference_url=None)))

    with pytest.raises(SystemExit) as raised:
        main([MorphCommand.SERVE, "--selection", str(tmp_path / "absent.yaml")], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED
    reported = capsys.readouterr().err
    assert "Serving nothing:" in reported
    assert "absent.yaml" in reported
    assert "Traceback" not in reported
    assert not bound


def test_the_repository_s_selection_file_is_one_the_process_can_serve() -> None:
    assert read_route_selection(DEFAULT_SELECTION_PATH).envelope is not None


def test_a_missing_configuration_ends_the_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "absent.toml"))

    with pytest.raises(SystemExit) as raised:
        main([MorphCommand.SERVE], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED
