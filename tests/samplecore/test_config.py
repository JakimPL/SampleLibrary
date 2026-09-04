from __future__ import annotations

from pathlib import Path

import pytest

from samplecore.config import (
    CONFIG_PATH_ENVIRONMENT_VARIABLE,
    DEFAULT_CONFIG_PATH,
    ConfigurationError,
    LibraryConfig,
    load_config,
)


def test_the_default_config_path_sits_next_to_the_committed_example_template() -> None:
    assert DEFAULT_CONFIG_PATH.name == "config.toml"
    assert (DEFAULT_CONFIG_PATH.parent / "config.example.toml").is_file()


def test_a_config_file_round_trips_through_load_config(tmp_path: Path) -> None:
    module_source_directory = tmp_path / "modules"
    library_root = tmp_path / "library"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"[library]\n"
        f'module_source_directory = "{module_source_directory.as_posix()}"\n'
        f'library_root = "{library_root.as_posix()}"\n',
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config == LibraryConfig(module_source_directory=module_source_directory, library_root=library_root)


def test_missing_optional_paths_are_derived_from_the_library_root(tmp_path: Path) -> None:
    library_root = tmp_path / "library"
    config = LibraryConfig(module_source_directory=tmp_path / "modules", library_root=library_root)

    assert config.resolved_database_path == library_root / "samplelibrary.duckdb"
    assert config.resolved_cloud_artifact_directory == library_root / "embeddings"


def test_explicit_optional_paths_override_the_derived_defaults(tmp_path: Path) -> None:
    database_path = tmp_path / "custom.duckdb"
    config = LibraryConfig(
        module_source_directory=tmp_path / "modules",
        library_root=tmp_path / "library",
        database_path=database_path,
    )

    assert config.resolved_database_path == database_path


def test_loading_a_missing_config_file_raises_a_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        load_config(tmp_path / "does-not-exist.toml")


def test_an_explicit_path_argument_takes_precedence_over_the_environment_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_source_directory = tmp_path / "modules"
    library_root = tmp_path / "library"
    explicit_path = tmp_path / "explicit.toml"
    explicit_path.write_text(
        f"[library]\n"
        f'module_source_directory = "{module_source_directory.as_posix()}"\n'
        f'library_root = "{library_root.as_posix()}"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "does-not-exist.toml"))

    config = load_config(explicit_path)

    assert config == LibraryConfig(module_source_directory=module_source_directory, library_root=library_root)


def test_the_environment_variable_is_used_when_no_explicit_path_is_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_source_directory = tmp_path / "modules"
    library_root = tmp_path / "library"
    environment_path = tmp_path / "from-environment.toml"
    environment_path.write_text(
        f"[library]\n"
        f'module_source_directory = "{module_source_directory.as_posix()}"\n'
        f'library_root = "{library_root.as_posix()}"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(environment_path))

    config = load_config()

    assert config == LibraryConfig(module_source_directory=module_source_directory, library_root=library_root)
