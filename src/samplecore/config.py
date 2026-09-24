from __future__ import annotations

import os
import shutil
import tomllib
from pathlib import Path
from typing import Final
from urllib.parse import SplitResult, urlsplit

from platformdirs import user_config_path, user_music_path
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from samplecore.storage.cluster.embedded.state import managed_catalog_url

APPLICATION_NAME: Final[str] = "SampleLibrary"
CONFIG_FILE_NAME: Final[str] = "config.toml"
SOURCE_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
EXAMPLE_CONFIG_PATH: Final[Path] = SOURCE_ROOT / "config.example.toml"
LIBRARY_DIRECTORY_NAME: Final[str] = "SampleLibrary"
CONFIG_PATH_ENVIRONMENT_VARIABLE: Final[str] = "SAMPLELIBRARY_CONFIG"
DATABASE_URL_ENVIRONMENT_VARIABLE: Final[str] = "SAMPLELIBRARY_DATABASE_URL"
DEFAULT_MINIMUM_SAMPLE_FRAMES: Final[int] = 512
DEFAULT_SAMPLE_DIRECTORIES: Final[tuple[Path, ...]] = ()
DEFAULT_SAMPLE_EXCLUSIONS: Final[tuple[str, ...]] = ()
DEFAULT_INFERENCE_URL: Final[str] = "http://127.0.0.1:8010"
LIBRARY_TABLE: Final[str] = "library"
INFERENCE_TABLE: Final[str] = "inference"
# The pipeline reads its own table, since what it holds is named by the steps rather than by the
# settings every command shares.
PIPELINE_TABLE: Final[str] = "pipeline"
INFERENCE_SCHEME: Final[str] = "http"
CONFIG_RELATIVE_PATH_SETTINGS: Final[tuple[str, ...]] = ("module_source_directory", "library_root")
CONFIG_RELATIVE_PATH_LIST_SETTINGS: Final[tuple[str, ...]] = ("sample_directories",)

# The example file's own stand-in paths. A config still carrying one has been copied but not yet
# filled in, and saying so is far more use than whatever the first pipeline to walk that path would
# report instead.
PLACEHOLDER_PATH_PREFIX: Final[str] = "/path/to/your"


class ConfigurationError(Exception):
    """Raised when the local library configuration cannot be found or does not validate."""


class InferenceConfig(BaseModel):
    """Where the morph inference process listens: the process binds this address and the API dials it.

    Both ends read the one URL, so it spells out everything each of them needs: the plain HTTP the
    process serves, a host and a port, and nothing past the root, where the process's routes live.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str = DEFAULT_INFERENCE_URL

    @field_validator("url")
    @classmethod
    def _names_a_bindable_address(cls, url: str) -> str:
        parts = urlsplit(url)
        if parts.scheme != INFERENCE_SCHEME:
            raise ValueError(f"{url} must use {INFERENCE_SCHEME}://, as in {DEFAULT_INFERENCE_URL}")
        if parts.path not in ("", "/") or parts.query or parts.fragment:
            raise ValueError(f"{url} must name the process's root, as in {DEFAULT_INFERENCE_URL}")
        _required_host(parts)
        _required_port(parts)
        return url

    @property
    def host(self) -> str:
        """The address the inference process binds and the API dials."""
        return _required_host(urlsplit(self.url))

    @property
    def port(self) -> int:
        """The port the inference process binds and the API dials."""
        return _required_port(urlsplit(self.url))


class LibraryConfig(BaseModel):
    """Local, machine-specific configuration this project reads at startup.

    Nothing here is checked into the repository. ``library_root`` is required with no default, since
    fabricating a plausible-looking value would point the library at the wrong place silently rather
    than failing loudly when configuration is missing. ``module_source_directory`` names the tracker
    module collection, and a library built from sample folders alone leaves it out.
    ``database_url`` names a Postgres server of a person's own; left out, the library keeps a managed
    server inside its library root, which the application creates and runs. The inference address
    has a default, since one machine running both processes is the common case and the port is free
    to choose.

    ``sample_directories`` names folders of plain audio files the library reads in place, beside the
    samples it extracts from modules, and ``sample_exclusions`` holds the patterns naming what inside
    them stays out of the library. The catalog records each file by its directory and its path within
    it, so every directory is absolute and stands apart from the others, which gives one file exactly
    one place in the catalog.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    module_source_directory: Path | None = None
    library_root: Path
    database_url: str | None = None
    minimum_sample_frames: int = DEFAULT_MINIMUM_SAMPLE_FRAMES
    sample_directories: tuple[Path, ...] = DEFAULT_SAMPLE_DIRECTORIES
    sample_exclusions: tuple[str, ...] = DEFAULT_SAMPLE_EXCLUSIONS
    inference: InferenceConfig = InferenceConfig()

    @field_validator("sample_directories")
    @classmethod
    def _names_separate_absolute_directories(cls, directories: tuple[Path, ...]) -> tuple[Path, ...]:
        for directory in directories:
            if not directory.is_absolute():
                raise ValueError(f"{directory} must be an absolute path")
        for index, directory in enumerate(directories):
            for other in directories[index + 1 :]:
                if directory.is_relative_to(other) or other.is_relative_to(directory):
                    raise ValueError(f"{directory} and {other} overlap; name each folder of samples once")
        return directories

    @field_validator("sample_exclusions")
    @classmethod
    def _holds_patterns(cls, exclusions: tuple[str, ...]) -> tuple[str, ...]:
        if any(not pattern.strip() for pattern in exclusions):
            raise ValueError("an exclusion must be a pattern such as *loop*")
        return exclusions

    @field_validator("database_url")
    @classmethod
    def _parses_as_a_database_url(cls, database_url: str | None) -> str | None:
        """Read the URL the way every connection will, importing the database stack only once a config loads.

        The command line imports this module to list its commands, and that listing stays as light as
        the settings' names.
        """
        # pylint: disable=import-outside-toplevel
        from sqlalchemy.engine import make_url
        from sqlalchemy.exc import ArgumentError

        if database_url is None:
            return None
        try:
            make_url(database_url)
        except ArgumentError as error:
            raise ValueError(
                "must be a URL such as postgresql+psycopg://samplelibrary:samplelibrary@localhost:5432/samplelibrary"
            ) from error
        return database_url

    @property
    def manages_database(self) -> bool:
        """Whether the library keeps its own Postgres server inside its library root."""
        return self.database_url is None

    def catalog_url(self) -> str:
        """The URL every connection to the catalog opens: the configured server's, or the managed one's.

        Raises:
            ManagedClusterMissingError: the library manages its database and has not created it yet.
        """
        if self.database_url is not None:
            return self.database_url
        return managed_catalog_url(self.library_root)


def load_config(path: Path | None = None) -> LibraryConfig:
    """Load and validate the local library configuration.

    The lookup order is an explicit ``path``, then the ``SAMPLELIBRARY_CONFIG`` environment
    variable, then `default_config_path` — the first of these that is actually
    provided wins, so a caller (a test, a CLI flag) can always be explicit about where to read
    from without an environment variable silently overriding it. ``database_url`` follows the same
    precedence separately: the ``SAMPLELIBRARY_DATABASE_URL`` environment variable, when set to a
    value, overrides whatever ``config.toml`` holds, so credentials can be supplied at deployment
    time (a Docker secret, a CI variable) without living in a config file at all. A relative path
    setting is read from the config file's own directory, which is where a person writing it stands.

    Raises:
        ConfigurationError: no config file exists at the resolved path, the file is not valid TOML,
            it holds a table or setting this project does not read, a setting fails validation, or
            the file still carries the example's stand-in paths.
    """
    resolved_path = resolve_config_path(path)
    if not resolved_path.is_file():
        raise ConfigurationError(
            f"No config file at {resolved_path}. Run `samplelibrary setup config` to put one there, or copy "
            "config.example.toml to config.toml yourself, and fill in your paths."
        )
    return parse_config(resolved_path.read_text(encoding="utf-8"), resolved_path)


def parse_config(content: str, config_path: Path) -> LibraryConfig:
    """Validate a config file's content as `load_config` reads the file at ``config_path``.

    For a writer checking what it is about to put in place, and for `load_config` itself.

    Raises:
        ConfigurationError: the content is not valid TOML, holds a table or setting this project does
            not read, fails validation, or still carries the example's stand-in paths.
    """
    data = _read_tables(content, config_path)
    library_data = _anchored_paths(_table(data, LIBRARY_TABLE, config_path), config_path.parent.resolve())
    database_url_from_environment = os.environ.get(DATABASE_URL_ENVIRONMENT_VARIABLE)
    if database_url_from_environment:
        library_data["database_url"] = database_url_from_environment
    library_data[INFERENCE_TABLE] = _table(data, INFERENCE_TABLE, config_path)
    try:
        config = LibraryConfig.model_validate(library_data)
    except ValidationError as error:
        raise ConfigurationError(_describe_invalid_fields(error, config_path)) from error
    _reject_placeholder_paths(config, config_path)
    return config


def resolve_config_path(path: Path | None = None) -> Path:
    """The config file a command reads: ``path`` when given, then ``SAMPLELIBRARY_CONFIG``, then the default."""
    return path or _config_path_from_environment() or default_config_path()


def default_config_path() -> Path:
    """The config file read when nothing names one: a source checkout's own, or the one in the user's settings folder.

    A checkout holds the committed example beside the file a developer fills in, and an installed
    application keeps its file where the system keeps each user's settings.
    """
    if EXAMPLE_CONFIG_PATH.is_file():
        return SOURCE_ROOT / CONFIG_FILE_NAME
    return user_config_path(APPLICATION_NAME, appauthor=False) / CONFIG_FILE_NAME


def default_library_root() -> Path:
    """The library root the application suggests to a person choosing one: a folder in their music folder."""
    return user_music_path() / LIBRARY_DIRECTORY_NAME


def create_config_file(path: Path) -> bool:
    """Put a config file at ``path`` from the committed example, reporting whether it wrote one.

    A file already there is left exactly as it is, which is what lets this run on every install
    without a person's own paths ever being overwritten.

    Raises:
        ConfigurationError: the example this copies from is absent, or the directory ``path`` names is.
    """
    if path.exists():
        return False

    if not EXAMPLE_CONFIG_PATH.is_file():
        raise ConfigurationError(f"No example config to copy from at {EXAMPLE_CONFIG_PATH}.")
    if not path.parent.is_dir():
        raise ConfigurationError(f"No directory {path.parent} to put a config file in; create it first.")

    shutil.copyfile(EXAMPLE_CONFIG_PATH, path)
    return True


def _read_tables(content: str, config_path: Path) -> dict[str, object]:
    """The file's top-level tables, each of them one this project reads.

    The pipeline's own table is read by the pipeline rather than here, since the steps it names
    settle what belongs in it.

    Raises:
        ConfigurationError: the file is not valid TOML, or it holds a table this project does not read.
    """
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError as error:
        raise ConfigurationError(f"{config_path} is not valid TOML: {error}") from error

    unknown_tables = sorted(set(data) - {LIBRARY_TABLE, INFERENCE_TABLE, PIPELINE_TABLE})
    if unknown_tables:
        raise ConfigurationError(
            f"{config_path} holds settings this project does not read: {', '.join(unknown_tables)}. "
            f"Settings belong under [{LIBRARY_TABLE}], [{INFERENCE_TABLE}] and [{PIPELINE_TABLE}]."
        )
    return data


def _table(data: dict[str, object], name: str, config_path: Path) -> dict[str, object]:
    """One table's settings, empty when the file leaves the table out.

    Raises:
        ConfigurationError: the name holds a single value where a table belongs.
    """
    match data.get(name, {}):
        case dict() as table:
            return {str(key): value for key, value in table.items()}
        case _:
            raise ConfigurationError(f"{config_path} sets {name} to a single value; write it as a [{name}] table.")


def _anchored_paths(library_data: dict[str, object], config_directory: Path) -> dict[str, object]:
    """The library settings with each relative path read from the directory holding the config file."""
    anchored = dict(library_data)
    for name in CONFIG_RELATIVE_PATH_SETTINGS:
        match anchored.get(name):
            case str() as raw_path:
                anchored[name] = _anchored_path(raw_path, config_directory)
            case _:
                pass
    for name in CONFIG_RELATIVE_PATH_LIST_SETTINGS:
        match anchored.get(name):
            case list() as raw_paths:
                anchored[name] = [
                    _anchored_path(raw_path, config_directory) if isinstance(raw_path, str) else raw_path
                    for raw_path in raw_paths
                ]
            case _:
                pass
    return anchored


def _anchored_path(raw_path: str, config_directory: Path) -> str:
    return raw_path if Path(raw_path).is_absolute() else str(config_directory / raw_path)


def _required_host(parts: SplitResult) -> str:
    """The host a URL names.

    Raises:
        ValueError: the URL names no host.
    """
    if parts.hostname is None:
        raise ValueError(f"{parts.geturl()} names no host, as in {DEFAULT_INFERENCE_URL}")
    return parts.hostname


def _required_port(parts: SplitResult) -> int:
    """The port a URL names.

    Raises:
        ValueError: the URL leaves its port to the scheme's default.
    """
    if parts.port is None:
        raise ValueError(f"{parts.geturl()} names no port, as in {DEFAULT_INFERENCE_URL}")
    return parts.port


def _reject_placeholder_paths(config: LibraryConfig, resolved_path: Path) -> None:
    """Insist on a config whose paths a person has chosen.

    Raises:
        ConfigurationError: a path still holds the example's stand-in.
    """
    placeholders = dict.fromkeys(
        name
        for name, value in (
            *((("module_source_directory", config.module_source_directory),) if config.module_source_directory else ()),
            ("library_root", config.library_root),
            *(("sample_directories", directory) for directory in config.sample_directories),
        )
        if value.as_posix().startswith(PLACEHOLDER_PATH_PREFIX)
    )
    if placeholders:
        raise ConfigurationError(
            f"{resolved_path} still carries the example's stand-in path for {', '.join(placeholders)}. "
            "Open it and name your own module collection and library directories."
        )


def _describe_invalid_fields(error: ValidationError, config_path: Path) -> str:
    """Name every setting that failed validation, and where the database can come from besides the file."""
    problems = "; ".join(
        f"{'.'.join(str(part) for part in detail['loc'])}: {detail['msg']}" for detail in error.errors()
    )
    database_hint = (
        f" A command run without --config also reads the database from {DATABASE_URL_ENVIRONMENT_VARIABLE}."
        if any(detail["loc"][:1] == ("database_url",) for detail in error.errors())
        else ""
    )
    return f"{config_path} needs correcting: {problems}.{database_hint}"


def _config_path_from_environment() -> Path | None:
    raw_path = os.environ.get(CONFIG_PATH_ENVIRONMENT_VARIABLE)
    return Path(raw_path) if raw_path else None
