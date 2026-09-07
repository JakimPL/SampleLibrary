from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import sampleserver.main as main_module
from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE


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
