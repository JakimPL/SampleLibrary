from __future__ import annotations

from pathlib import Path

import pytest

from samplecore.cli_support import load_config_or_exit
from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE, LibraryConfig


def test_load_config_or_exit_returns_the_loaded_configuration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_source_directory = tmp_path / "modules"
    library_root = tmp_path / "library"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"[library]\n"
        f'module_source_directory = "{module_source_directory.as_posix()}"\n'
        f'library_root = "{library_root.as_posix()}"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))

    config = load_config_or_exit()

    assert config == LibraryConfig(module_source_directory=module_source_directory, library_root=library_root)


def test_load_config_or_exit_reports_a_missing_config_file_and_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "does-not-exist.toml"))

    with pytest.raises(SystemExit) as raised:
        load_config_or_exit()

    assert raised.value.code == 1
    assert "Configuration error" in capsys.readouterr().err
