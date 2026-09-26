from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE, DEFAULT_INFERENCE_URL
from sampleserver.frontend import FRONTEND_DIRECTORY_ENVIRONMENT_VARIABLE, INDEX_DOCUMENT

MAIN_MODULE = "sampleserver.main"


def _loaded_main() -> ModuleType:
    """The ASGI module built afresh from the config the test names, since it builds its app as it is imported."""
    if MAIN_MODULE in sys.modules:
        return importlib.reload(sys.modules[MAIN_MODULE])
    return importlib.import_module(MAIN_MODULE)


def test_main_builds_the_app_from_the_configured_reader_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[library]\nmodule_source_directory = "{tmp_path.as_posix()}"\nlibrary_root = "{tmp_path.as_posix()}"\n'
        'database_url = "postgresql+psycopg://user:pass@host/db"\n'
        'server_database_url = "postgresql+psycopg://reader:pass@host/db"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))

    main_module = _loaded_main()

    assert main_module.app.state.database_url == "postgresql+psycopg://reader:pass@host/db"
    assert main_module.app.state.library_root == tmp_path
    assert main_module.app.state.inference_url == DEFAULT_INFERENCE_URL


def test_main_serves_the_frontend_the_environment_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[library]\nmodule_source_directory = "{tmp_path.as_posix()}"\nlibrary_root = "{tmp_path.as_posix()}"\n'
        'database_url = "postgresql+psycopg://user:pass@host/db"\n'
        'server_database_url = "postgresql+psycopg://reader:pass@host/db"\n',
        encoding="utf-8",
    )
    built = tmp_path / "dist"
    built.mkdir()
    (built / INDEX_DOCUMENT).write_text("<!doctype html>", encoding="utf-8")
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))
    monkeypatch.setenv(FRONTEND_DIRECTORY_ENVIRONMENT_VARIABLE, str(built))

    main_module = _loaded_main()

    assert any(getattr(route, "name", None) == "frontend" for route in main_module.app.routes)
