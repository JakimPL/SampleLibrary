from __future__ import annotations

from pathlib import Path

import pydantic
import pytest

from samplecore.config import (
    CONFIG_PATH_ENVIRONMENT_VARIABLE,
    DATABASE_URL_ENVIRONMENT_VARIABLE,
    DEFAULT_CONFIG_PATH,
    EXAMPLE_CONFIG_PATH,
    ConfigurationError,
    LibraryConfig,
    create_config_file,
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
        f'library_root = "{library_root.as_posix()}"\n'
        f'database_url = "postgresql+psycopg://user:pass@host/db"\n',
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config == LibraryConfig(
        module_source_directory=module_source_directory,
        library_root=library_root,
        database_url="postgresql+psycopg://user:pass@host/db",
    )


def test_database_url_is_required(tmp_path: Path) -> None:
    with pytest.raises(pydantic.ValidationError):
        LibraryConfig(module_source_directory=tmp_path / "modules", library_root=tmp_path / "library")


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
        f'library_root = "{library_root.as_posix()}"\n'
        f'database_url = "postgresql+psycopg://user:pass@host/db"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "does-not-exist.toml"))

    config = load_config(explicit_path)

    assert config.module_source_directory == module_source_directory
    assert config.library_root == library_root


def test_the_environment_variable_is_used_when_no_explicit_path_is_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_source_directory = tmp_path / "modules"
    library_root = tmp_path / "library"
    environment_path = tmp_path / "from-environment.toml"
    environment_path.write_text(
        f"[library]\n"
        f'module_source_directory = "{module_source_directory.as_posix()}"\n'
        f'library_root = "{library_root.as_posix()}"\n'
        f'database_url = "postgresql+psycopg://user:pass@host/db"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(environment_path))

    config = load_config()

    assert config.module_source_directory == module_source_directory
    assert config.library_root == library_root


def test_database_url_environment_variable_overrides_the_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"[library]\n"
        f'module_source_directory = "{(tmp_path / "modules").as_posix()}"\n'
        f'library_root = "{(tmp_path / "library").as_posix()}"\n'
        f'database_url = "postgresql+psycopg://from-config-file/db"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(DATABASE_URL_ENVIRONMENT_VARIABLE, "postgresql+psycopg://from-environment/db")

    config = load_config(config_path)

    assert config.database_url == "postgresql+psycopg://from-environment/db"


def test_create_config_file_copies_the_example_where_no_config_is_there(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"

    created = create_config_file(config_path)

    assert created
    assert config_path.read_text(encoding="utf-8") == EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8")


def test_create_config_file_keeps_a_config_already_there(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[library]\n", encoding="utf-8")

    created = create_config_file(config_path)

    assert not created
    assert config_path.read_text(encoding="utf-8") == "[library]\n"


def test_the_committed_example_is_a_config_a_person_still_has_to_fill_in(tmp_path: Path) -> None:
    """Copying the example and running is what the placeholder check exists to catch."""
    config_path = tmp_path / "config.toml"
    create_config_file(config_path)

    with pytest.raises(ConfigurationError):
        load_config(config_path)


def test_a_config_naming_one_stand_in_path_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[library]\n"
        'module_source_directory = "/path/to/your/module/collection"\n'
        f'library_root = "{(tmp_path / "library").as_posix()}"\n'
        'database_url = "postgresql+psycopg://samplelibrary:samplelibrary@localhost:5432/samplelibrary"\n',
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError):
        load_config(config_path)
