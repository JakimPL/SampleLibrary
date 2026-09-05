from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import sampleserver.main as main_module
from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE, DEFAULT_DATABASE_FILENAME


def test_main_builds_the_app_from_the_configured_database_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[library]\nmodule_source_directory = "{tmp_path.as_posix()}"\nlibrary_root = "{tmp_path.as_posix()}"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))

    importlib.reload(main_module)

    assert main_module.app.state.database_path == tmp_path / DEFAULT_DATABASE_FILENAME
    assert main_module.app.state.library_root == tmp_path
