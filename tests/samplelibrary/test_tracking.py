from __future__ import annotations

from pathlib import Path

import pytest

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from samplecore.tracking.store import tracking_uri
from samplelibrary import tracking

PROGRAM = "samplelibrary tracking uri"


def test_the_uri_is_the_only_line_printed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    library_root = tmp_path / "library"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[library]\n"
        f'module_source_directory = "{(tmp_path / "modules").as_posix()}"\n'
        f'library_root = "{library_root.as_posix()}"\n'
        'database_url = "postgresql+psycopg://user:pass@host/db"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))

    tracking.main([], prog=PROGRAM)

    assert capsys.readouterr().out.splitlines() == [tracking_uri(library_root)]


def test_a_missing_configuration_ends_the_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "absent.toml"))

    with pytest.raises(SystemExit) as raised:
        tracking.main([], prog=PROGRAM)

    assert raised.value.code == 1
