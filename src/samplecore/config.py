from __future__ import annotations

import os
import shutil
import tomllib
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

DEFAULT_CONFIG_PATH: Final[Path] = Path(__file__).resolve().parents[2] / "config.toml"
EXAMPLE_CONFIG_PATH: Final[Path] = Path(__file__).resolve().parents[2] / "config.example.toml"
CONFIG_PATH_ENVIRONMENT_VARIABLE: Final[str] = "SAMPLELIBRARY_CONFIG"
DATABASE_URL_ENVIRONMENT_VARIABLE: Final[str] = "SAMPLELIBRARY_DATABASE_URL"
DEFAULT_MINIMUM_SAMPLE_FRAMES: Final[int] = 512

# The example file's own stand-in paths. A config still carrying one has been copied but not yet
# filled in, and saying so is far more use than whatever the first pipeline to walk that path would
# report instead.
PLACEHOLDER_PATH_PREFIX: Final[str] = "/path/to/your"


class ConfigurationError(Exception):
    """Raised when the local library configuration cannot be found or does not validate."""


class LibraryConfig(BaseModel):
    """Local, machine-specific configuration this project reads at startup.

    Nothing here is checked into the repository. ``module_source_directory``, ``library_root``, and
    ``database_url`` are required with no default, since fabricating a plausible-looking value would
    point the library at the wrong place, or the wrong database, silently rather than failing loudly
    when configuration is missing.
    """

    model_config = ConfigDict(frozen=True)

    module_source_directory: Path
    library_root: Path
    database_url: str
    minimum_sample_frames: int = DEFAULT_MINIMUM_SAMPLE_FRAMES


def load_config(path: Path | None = None) -> LibraryConfig:
    """Load and validate the local library configuration.

    The lookup order is an explicit ``path``, then the ``SAMPLELIBRARY_CONFIG`` environment
    variable, then ``config.toml`` at the repository root — the first of these that is actually
    provided wins, so a caller (a test, a CLI flag) can always be explicit about where to read
    from without an environment variable silently overriding it. ``database_url`` follows the same
    precedence separately: the ``SAMPLELIBRARY_DATABASE_URL`` environment variable, when set,
    overrides whatever ``config.toml`` holds, so credentials can be supplied at deployment time (a
    Docker secret, a CI variable) without living in a config file at all.

    Raises:
        ConfigurationError: no config file exists at the resolved path, or the file still carries
            the example's stand-in paths.
    """
    resolved_path = path or _config_path_from_environment() or DEFAULT_CONFIG_PATH
    if not resolved_path.is_file():
        raise ConfigurationError(
            f"No config file at {resolved_path}. Run `make install` to put one there, or copy "
            "config.example.toml to config.toml yourself, and fill in your paths."
        )
    with resolved_path.open("rb") as config_file:
        data = tomllib.load(config_file)
    library_data = dict(data.get("library", {}))
    database_url_from_environment = os.environ.get(DATABASE_URL_ENVIRONMENT_VARIABLE)
    if database_url_from_environment is not None:
        library_data["database_url"] = database_url_from_environment
    config = LibraryConfig.model_validate(library_data)
    _reject_placeholder_paths(config, resolved_path)
    return config


def create_config_file(path: Path) -> bool:
    """Put a config file at ``path`` from the committed example, reporting whether it wrote one.

    A file already there is left exactly as it is, which is what lets this run on every install
    without a person's own paths ever being overwritten.

    Raises:
        ConfigurationError: the example this copies from is absent.
    """
    if path.exists():
        return False

    if not EXAMPLE_CONFIG_PATH.is_file():
        raise ConfigurationError(f"No example config to copy from at {EXAMPLE_CONFIG_PATH}.")

    shutil.copyfile(EXAMPLE_CONFIG_PATH, path)
    return True


def _reject_placeholder_paths(config: LibraryConfig, resolved_path: Path) -> None:
    """Insist on a config whose paths a person has chosen.

    Raises:
        ConfigurationError: a path still holds the example's stand-in.
    """
    placeholders = tuple(
        name
        for name, value in (
            ("module_source_directory", config.module_source_directory),
            ("library_root", config.library_root),
        )
        if value.as_posix().startswith(PLACEHOLDER_PATH_PREFIX)
    )
    if placeholders:
        raise ConfigurationError(
            f"{resolved_path} still carries the example's stand-in path for {', '.join(placeholders)}. "
            "Open it and name your own module collection and library directories."
        )


def _config_path_from_environment() -> Path | None:
    raw_path = os.environ.get(CONFIG_PATH_ENVIRONMENT_VARIABLE)
    return Path(raw_path) if raw_path else None
