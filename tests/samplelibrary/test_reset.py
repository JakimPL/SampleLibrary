from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path

import pytest

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE, DATABASE_URL_ENVIRONMENT_VARIABLE
from samplelibrary import reset

PROGRAM = "samplelibrary reset"
CONFIG_PASSWORD = "unshown-password"
TARGET_DATABASE = "reset-target"


@pytest.fixture
def library_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "catalog"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[library]\n"
        f'module_source_directory = "{(tmp_path / "modules").as_posix()}"\n'
        f'library_root = "{root.as_posix()}"\n'
        f'database_url = "postgresql+psycopg://samplelibrary:{CONFIG_PASSWORD}@localhost:5432/{TARGET_DATABASE}"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))
    monkeypatch.delenv(DATABASE_URL_ENVIRONMENT_VARIABLE, raising=False)
    return root


def test_confirm_flag_defaults_to_false() -> None:
    arguments = reset._parse_arguments([], prog=PROGRAM)

    assert arguments.confirm is False


def test_confirm_flag_can_be_set() -> None:
    arguments = reset._parse_arguments(["--confirm"], prog=PROGRAM)

    assert arguments.confirm is True


def test_main_without_confirm_empties_nothing(library_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    emptied: list[Path] = []
    monkeypatch.setattr(reset, "reset_library", lambda connection, root: emptied.append(root))

    reset.main([], prog=PROGRAM)

    assert not emptied


def test_main_without_confirm_names_the_library_and_database_it_would_empty(
    library_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    reset.main([], prog=PROGRAM)

    report = capsys.readouterr().out
    assert str(library_root) in report
    assert TARGET_DATABASE in report
    assert CONFIG_PASSWORD not in report


def test_main_with_confirm_empties_the_configured_library(library_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    emptied: list[Path] = []
    monkeypatch.setattr(reset, "open_catalog_connection", lambda database_url: nullcontext())
    monkeypatch.setattr(reset, "reset_library", lambda connection, root: emptied.append(root))

    reset.main(["--confirm"], prog=PROGRAM)

    assert emptied == [library_root]
