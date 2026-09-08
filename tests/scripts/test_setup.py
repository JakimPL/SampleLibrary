from __future__ import annotations

import importlib.util
import types
from pathlib import Path

import pytest

from samplecore.config import EXAMPLE_CONFIG_PATH

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "setup.py"

_UNREACHABLE_SERVER_URL = "postgresql+psycopg://samplelibrary:samplelibrary@localhost:1/samplelibrary"


def _load_script(path: Path, name: str) -> types.ModuleType:
    """Imports a script by file path -- it lives outside every installed package, by design."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


setup = _load_script(_SCRIPT_PATH, "setup")


def test_config_writes_a_file_where_none_is_there(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr(setup, "DEFAULT_CONFIG_PATH", config_path)

    setup.main(["config"])

    assert config_path.read_text(encoding="utf-8") == EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8")


def test_config_keeps_a_file_already_there(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A person's own paths outlive every later install."""
    config_path = tmp_path / "config.toml"
    config_path.write_text('[library]\nlibrary_root = "/somewhere/of/my/own"\n', encoding="utf-8")
    monkeypatch.setattr(setup, "DEFAULT_CONFIG_PATH", config_path)

    setup.main(["config"])

    assert "/somewhere/of/my/own" in config_path.read_text(encoding="utf-8")


def test_database_reports_what_to_do_about_a_server_it_cannot_reach(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[library]\n"
        f'module_source_directory = "{tmp_path / "modules"}"\n'
        f'library_root = "{tmp_path / "library"}"\n'
        f'database_url = "{_UNREACHABLE_SERVER_URL}"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("SAMPLELIBRARY_CONFIG", str(config_path))
    monkeypatch.delenv("SAMPLELIBRARY_DATABASE_URL", raising=False)
    monkeypatch.delenv("SAMPLELIBRARY_ADMIN_DATABASE_URL", raising=False)

    with pytest.raises(SystemExit) as exit_info:
        setup.main(["database"])

    assert exit_info.value.code == 1
    assert "docker compose up -d postgres" in capsys.readouterr().err


def test_database_insists_on_a_config_whose_paths_are_filled_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A scaffolded config that nobody edited fails here, where the message still explains itself."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("SAMPLELIBRARY_CONFIG", str(config_path))

    with pytest.raises(SystemExit) as exit_info:
        setup.main(["database"])

    assert exit_info.value.code == 1
    assert "stand-in path" in capsys.readouterr().err
