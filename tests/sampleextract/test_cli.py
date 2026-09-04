from __future__ import annotations

from pathlib import Path

import pytest

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from sampleextract.cli import main


def _write_config(tmp_path: Path) -> Path:
    module_source_directory = tmp_path / "modules"
    module_source_directory.mkdir()
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[library]\n"
        f'module_source_directory = "{module_source_directory.as_posix()}"\n'
        f'library_root = "{(tmp_path / "library").as_posix()}"\n',
        encoding="utf-8",
    )
    return config_path


def test_main_reports_a_configuration_error_and_exits_without_a_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "does-not-exist.toml"))

    with pytest.raises(SystemExit) as raised:
        main()

    assert raised.value.code == 1
    assert "Configuration error" in capsys.readouterr().err


def test_main_creates_the_library_root_and_reports_an_empty_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path)))

    main()

    assert (tmp_path / "library").is_dir()
    assert "Discovered 0 modules" in capsys.readouterr().out


def test_main_exits_with_an_error_status_and_lists_every_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = _write_config(tmp_path)
    (tmp_path / "modules" / "corrupt.xm").write_bytes(b"not a real module file")
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))

    with pytest.raises(SystemExit) as raised:
        main()

    assert raised.value.code == 1
    assert "corrupt.xm" in capsys.readouterr().out
