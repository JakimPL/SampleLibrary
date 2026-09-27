from __future__ import annotations

import re
from pathlib import Path

import pytest

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE, PASSWORD_PLACEHOLDER
from samplecore.exit_status import ExitStatus
from samplecore.paths import EXAMPLE_CONFIG_PATH
from sampleripper import setup
from sampleripper.cli import dispatch

PROGRAM = "sampleripper setup"

_UNREACHABLE_SERVER_URL = "postgresql+psycopg://sampleripper:not-a-real-password@localhost:1/sampleripper"


def test_config_writes_a_file_where_none_is_there(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))

    setup.main(["config"], prog=PROGRAM)

    assert _as_example(config_path) == EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8")


def test_config_writes_the_file_the_command_line_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "elsewhere.toml"))
    config_path = tmp_path / "sandbox.toml"

    dispatch(["--config", str(config_path), "setup", "config"])

    assert _as_example(config_path) == EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8")
    assert not (tmp_path / "elsewhere.toml").exists()


def _as_example(config_path: Path) -> str:
    """A written config with each password it chose put back as the example's stand-in."""
    return re.sub(r":[\w-]+@", f":{PASSWORD_PLACEHOLDER}@", config_path.read_text(encoding="utf-8"))


def test_config_keeps_a_file_already_there(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A person's own paths outlive every later install."""
    config_path = tmp_path / "config.toml"
    config_path.write_text('[library]\nlibrary_root = "/somewhere/of/my/own"\n', encoding="utf-8")
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))

    setup.main(["config"], prog=PROGRAM)

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
    monkeypatch.setenv("SAMPLERIPPER_CONFIG", str(config_path))
    monkeypatch.delenv("SAMPLERIPPER_DATABASE_URL", raising=False)
    monkeypatch.delenv("SAMPLERIPPER_ADMIN_DATABASE_URL", raising=False)

    with pytest.raises(SystemExit) as exit_info:
        setup.main(["database"], prog=PROGRAM)

    assert exit_info.value.code == 1
    assert "docker compose up -d postgres" in capsys.readouterr().err


def test_database_insists_on_a_config_whose_paths_are_filled_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A scaffolded config that nobody edited fails here, where the message still explains itself."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("SAMPLERIPPER_CONFIG", str(config_path))

    with pytest.raises(SystemExit) as exit_info:
        setup.main(["database"], prog=PROGRAM)

    assert exit_info.value.code == ExitStatus.REFUSED
    assert "stand-in path" in capsys.readouterr().err


def test_config_into_a_directory_that_is_not_there_ends_with_one_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "absent" / "config.toml"))

    with pytest.raises(SystemExit) as raised:
        setup.main(["config"], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED
    assert "No directory" in capsys.readouterr().err
