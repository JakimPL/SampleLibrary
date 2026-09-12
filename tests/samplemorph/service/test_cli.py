from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from samplemorph.service import cli

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
def recorded(monkeypatch: pytest.MonkeyPatch) -> RecordedRun:
    """Captures what the serve command hands uvicorn, in place of binding a socket."""
    run = RecordedRun()

    def record(application: FastAPI, *, host: str, port: int) -> None:
        run.application = application
        run.host = host
        run.port = port

    monkeypatch.setattr(cli.uvicorn, "run", record)
    return run


def test_the_process_binds_the_address_the_configuration_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, recorded: RecordedRun
) -> None:
    config_path = _write_config(tmp_path, inference_url=f"http://{CONFIGURED_HOST}:{CONFIGURED_PORT}")
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))

    cli.main(["--device", "cpu"])

    assert (recorded.host, recorded.port) == (CONFIGURED_HOST, CONFIGURED_PORT)
    assert recorded.application is not None
    assert recorded.application.state.settings.choice.device == "cpu"
    assert recorded.application.state.settings.library_root == tmp_path


def test_a_flag_overrides_the_configured_port_and_the_default_address_serves_when_none_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, recorded: RecordedRun
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, inference_url=None)))

    cli.main(["--port", str(OVERRIDING_PORT)])

    assert recorded.host == cli.FALLBACK_HOST
    assert recorded.port == OVERRIDING_PORT


def test_a_missing_configuration_ends_the_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "absent.toml"))

    with pytest.raises(SystemExit) as raised:
        cli.main([])

    assert raised.value.code == 1
