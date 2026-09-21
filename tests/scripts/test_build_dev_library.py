from __future__ import annotations

import importlib.util
import tomllib
import types
from pathlib import Path

import pytest

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE, DATABASE_URL_ENVIRONMENT_VARIABLE

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "build_dev_library.py"
LIBRARY_ON_ANOTHER_PORT = "postgresql+psycopg://someone:secret@localhost:5433/my_library"


def _load_build_dev_library() -> types.ModuleType:
    """Imports the script by file path -- it lives outside every installed package, by design."""
    spec = importlib.util.spec_from_file_location("build_dev_library", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_dev_library = _load_build_dev_library()


def test_the_sandbox_shares_the_configured_server_under_a_database_of_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[library]\n"
        f'module_source_directory = "{(tmp_path / "modules").as_posix()}"\n'
        f'library_root = "{(tmp_path / "library").as_posix()}"\n'
        f'database_url = "{LIBRARY_ON_ANOTHER_PORT}"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))
    monkeypatch.delenv(DATABASE_URL_ENVIRONMENT_VARIABLE, raising=False)

    build_dev_library.main(["--output", str(tmp_path / "sandbox"), "--target-module-count", "13"])

    with (tmp_path / "sandbox" / "config.toml").open("rb") as config_file:
        sandbox_url = tomllib.load(config_file)["library"]["database_url"]
    assert sandbox_url == "postgresql+psycopg://someone:secret@localhost:5433/samplelibrary_dev"
