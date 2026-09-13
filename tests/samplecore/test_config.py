from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pydantic
import pytest

from samplecore.config import (
    CONFIG_PATH_ENVIRONMENT_VARIABLE,
    DATABASE_URL_ENVIRONMENT_VARIABLE,
    DEFAULT_CONFIG_PATH,
    EXAMPLE_CONFIG_PATH,
    ConfigurationError,
    InferenceConfig,
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


def test_the_inference_address_is_read_from_its_own_table(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[library]\nmodule_source_directory = "{(tmp_path / "modules").as_posix()}"\n'
        f'library_root = "{(tmp_path / "library").as_posix()}"\n'
        'database_url = "postgresql+psycopg://user:pass@host/db"\n'
        '[inference]\nurl = "http://render.local:9000"\n',
        encoding="utf-8",
    )

    assert load_config(config_path).inference.url == "http://render.local:9000"


def test_the_inference_address_has_a_default_when_the_table_is_absent(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[library]\nmodule_source_directory = "{(tmp_path / "modules").as_posix()}"\n'
        f'library_root = "{(tmp_path / "library").as_posix()}"\n'
        'database_url = "postgresql+psycopg://user:pass@host/db"\n',
        encoding="utf-8",
    )

    assert load_config(config_path).inference == InferenceConfig()


def test_database_url_is_required(tmp_path: Path) -> None:
    with pytest.raises(pydantic.ValidationError):
        LibraryConfig(module_source_directory=tmp_path / "modules", library_root=tmp_path / "library")


def test_a_config_missing_a_setting_names_it_in_a_configuration_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[library]\n"
        f'module_source_directory = "{(tmp_path / "modules").as_posix()}"\n'
        f'library_root = "{(tmp_path / "library").as_posix()}"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv(DATABASE_URL_ENVIRONMENT_VARIABLE, raising=False)

    with pytest.raises(ConfigurationError, match="database_url") as raised:
        load_config(config_path)

    assert DATABASE_URL_ENVIRONMENT_VARIABLE in str(raised.value)


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


def _library_table(tmp_path: Path) -> str:
    return (
        "[library]\n"
        f'module_source_directory = "{(tmp_path / "modules").as_posix()}"\n'
        f'library_root = "{(tmp_path / "library").as_posix()}"\n'
        'database_url = "postgresql+psycopg://user:pass@host/db"\n'
    )


@dataclass(frozen=True)
class RejectedConfigCase:
    content: str
    reason: str


@pytest.mark.parametrize(
    "case",
    [
        RejectedConfigCase(content='[library\nlibrary_root = "x"\n', reason="not valid TOML"),
        RejectedConfigCase(content="library = 3\n", reason="write it as a [library] table"),
        RejectedConfigCase(content='[renderer]\nurl = "x"\n', reason="renderer"),
    ],
    ids=("malformed TOML", "a value where a table belongs", "a table this project does not read"),
)
def test_a_config_file_this_project_cannot_read_is_a_configuration_error(
    tmp_path: Path, case: RejectedConfigCase
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(case.content, encoding="utf-8")

    with pytest.raises(ConfigurationError, match=re.escape(case.reason)):
        load_config(config_path)


def test_a_misspelled_setting_is_named_in_a_configuration_error(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(_library_table(tmp_path) + "minimum_sample_frame = 128\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="minimum_sample_frame"):
        load_config(config_path)


def test_a_database_url_that_does_not_parse_is_a_configuration_error(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[library]\n"
        f'module_source_directory = "{(tmp_path / "modules").as_posix()}"\n'
        f'library_root = "{(tmp_path / "library").as_posix()}"\n'
        'database_url = "not a url"\n',
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="database_url"):
        load_config(config_path)


def test_an_empty_database_url_variable_leaves_the_file_in_charge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(_library_table(tmp_path), encoding="utf-8")
    monkeypatch.setenv(DATABASE_URL_ENVIRONMENT_VARIABLE, "")

    assert load_config(config_path).database_url == "postgresql+psycopg://user:pass@host/db"


def test_relative_paths_are_read_from_the_config_files_directory(tmp_path: Path) -> None:
    config_directory = tmp_path / "sandbox"
    config_directory.mkdir()
    config_path = config_directory / "config.toml"
    config_path.write_text(
        '[library]\nmodule_source_directory = "modules"\nlibrary_root = "catalog"\n'
        'database_url = "postgresql+psycopg://user:pass@host/db"\n',
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.module_source_directory == config_directory / "modules"
    assert config.library_root == config_directory / "catalog"


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1", "https://127.0.0.1:8010", "http://127.0.0.1:8010/renderer", "http://:8010"],
    ids=("no port", "encrypted scheme", "a path past the root", "no host"),
)
def test_an_inference_address_both_ends_cannot_share_is_refused(url: str) -> None:
    with pytest.raises(pydantic.ValidationError):
        InferenceConfig(url=url)


def test_the_inference_address_names_its_host_and_port() -> None:
    inference = InferenceConfig(url="http://render.local:9000/")

    assert (inference.host, inference.port) == ("render.local", 9000)
