from __future__ import annotations

import argparse
import io
from dataclasses import dataclass
from pathlib import Path

import pytest

from samplecore.cli_support import (
    bootstrap_cli,
    configure_console_output_encoding,
    integer_at_least,
    integer_between,
    load_config_or_exit,
    positive_multiple_of,
)
from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE, LibraryConfig
from samplecore.exit_status import ExitStatus


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

    assert raised.value.code == ExitStatus.REFUSED
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


@dataclass(frozen=True)
class RefusedIntegerCase:
    raw_value: str
    reason: str


@pytest.mark.parametrize(
    "case",
    [
        RefusedIntegerCase(raw_value="two", reason="whole number"),
        RefusedIntegerCase(raw_value="0", reason="at least 1"),
        RefusedIntegerCase(raw_value="11", reason="at most 10"),
    ],
    ids=("not a number", "below the floor", "above the ceiling"),
)
def test_a_bounded_integer_option_refuses_a_value_outside_its_bounds(case: RefusedIntegerCase) -> None:
    with pytest.raises(argparse.ArgumentTypeError, match=case.reason):
        integer_between(1, 10)(case.raw_value)


def test_a_bounded_integer_option_reads_a_value_on_its_bounds() -> None:
    assert [integer_between(1, 10)(raw_value) for raw_value in ("1", "10")] == [1, 10]
    assert integer_at_least(0)("0") == 0


def test_a_bounded_integer_option_is_reported_as_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    parser = argparse.ArgumentParser(prog="bounded")
    parser.add_argument("--workers", type=integer_at_least(1))

    with pytest.raises(SystemExit) as raised:
        parser.parse_args(["--workers", "0"])

    assert raised.value.code == 2
    assert "must be at least 1, not 0" in capsys.readouterr().err


@pytest.mark.parametrize(
    "case",
    [
        RefusedIntegerCase(raw_value="12", reason="multiple of 8"),
        RefusedIntegerCase(raw_value="0", reason="at least 8"),
    ],
    ids=("between steps", "no step at all"),
)
def test_a_stepped_option_refuses_a_value_off_its_steps(case: RefusedIntegerCase) -> None:
    with pytest.raises(argparse.ArgumentTypeError, match=case.reason):
        positive_multiple_of(8)(case.raw_value)


def test_a_stepped_option_reads_a_value_on_its_steps() -> None:
    assert positive_multiple_of(8)("48") == 48
