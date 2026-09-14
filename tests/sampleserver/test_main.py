from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import sampleserver.main as main_module
from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE, DEFAULT_INFERENCE_URL
from sampleserver.frontend import FRONTEND_DIRECTORY_ENVIRONMENT_VARIABLE, INDEX_DOCUMENT


def test_main_builds_the_app_from_the_configured_database_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[library]\nmodule_source_directory = "{tmp_path.as_posix()}"\nlibrary_root = "{tmp_path.as_posix()}"\n'
        'database_url = "postgresql+psycopg://user:pass@host/db"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))

    importlib.reload(main_module)

    assert main_module.app.state.database_url == "postgresql+psycopg://user:pass@host/db"
    assert main_module.app.state.library_root == tmp_path
    assert main_module.app.state.inference_url == DEFAULT_INFERENCE_URL


def test_main_serves_the_frontend_the_environment_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[library]\nmodule_source_directory = "{tmp_path.as_posix()}"\nlibrary_root = "{tmp_path.as_posix()}"\n'
        'database_url = "postgresql+psycopg://user:pass@host/db"\n',
        encoding="utf-8",
    )
    built = tmp_path / "dist"
    built.mkdir()
    (built / INDEX_DOCUMENT).write_text("<!doctype html>", encoding="utf-8")
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))
    monkeypatch.setenv(FRONTEND_DIRECTORY_ENVIRONMENT_VARIABLE, str(built))

    importlib.reload(main_module)

    assert any(getattr(route, "name", None) == "frontend" for route in main_module.app.routes)
