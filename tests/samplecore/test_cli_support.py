from __future__ import annotations

import io
from pathlib import Path

import pytest

from samplecore.cli_support import bootstrap_cli, configure_console_output_encoding, load_config_or_exit
from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE, LibraryConfig


def test_configure_console_output_encoding_lets_stdout_print_an_unencodable_character(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    narrow_stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp1250")
    monkeypatch.setattr("sys.stdout", narrow_stdout)

    configure_console_output_encoding()
    print("Moduły", file=narrow_stdout)

    narrow_stdout.flush()
    assert b"Modu" in narrow_stdout.buffer.getvalue()


def test_configure_console_output_encoding_leaves_a_non_text_wrapper_stream_alone(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_console_output_encoding()

    print("Moduły")

    assert "Moduły" in capsys.readouterr().out


def test_load_config_or_exit_returns_the_loaded_configuration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_source_directory = tmp_path / "modules"
    library_root = tmp_path / "library"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"[library]\n"
        f'module_source_directory = "{module_source_directory.as_posix()}"\n'
        f'library_root = "{library_root.as_posix()}"\n'
        f'database_url = "postgresql+psycopg://user:pass@host/db"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))

    config = load_config_or_exit()

    assert config == LibraryConfig(
        module_source_directory=module_source_directory,
        library_root=library_root,
        database_url="postgresql+psycopg://user:pass@host/db",
    )


def test_load_config_or_exit_reports_a_missing_config_file_and_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "does-not-exist.toml"))

    with pytest.raises(SystemExit) as raised:
        load_config_or_exit()

    assert raised.value.code == 1
    assert "Configuration error" in capsys.readouterr().err


def test_bootstrap_cli_configures_console_encoding_and_returns_the_loaded_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_source_directory = tmp_path / "modules"
    library_root = tmp_path / "library"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"[library]\n"
        f'module_source_directory = "{module_source_directory.as_posix()}"\n'
        f'library_root = "{library_root.as_posix()}"\n'
        f'database_url = "postgresql+psycopg://user:pass@host/db"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))
    narrow_stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp1250")
    monkeypatch.setattr("sys.stdout", narrow_stdout)

    config = bootstrap_cli()
    print("Moduły", file=narrow_stdout)
    narrow_stdout.flush()

    assert config == LibraryConfig(
        module_source_directory=module_source_directory,
        library_root=library_root,
        database_url="postgresql+psycopg://user:pass@host/db",
    )
    assert b"Modu" in narrow_stdout.buffer.getvalue()
