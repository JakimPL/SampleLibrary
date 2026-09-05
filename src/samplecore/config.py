from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

DEFAULT_CONFIG_PATH: Final[Path] = Path(__file__).resolve().parents[2] / "config.toml"
CONFIG_PATH_ENVIRONMENT_VARIABLE: Final[str] = "SAMPLELIBRARY_CONFIG"
DEFAULT_DATABASE_FILENAME: Final[str] = "samplelibrary.duckdb"
DEFAULT_CLOUD_ARTIFACT_DIRECTORY_NAME: Final[str] = "embeddings"
DEFAULT_MINIMUM_SAMPLE_FRAMES: Final[int] = 512


class ConfigurationError(Exception):
    """Raised when the local library configuration cannot be found or does not validate."""


class LibraryConfig(BaseModel):
    """Local, machine-specific configuration this project reads at startup.

    Nothing here is checked into the repository. ``module_source_directory`` and
    ``library_root`` are required with no default, since fabricating a plausible-looking path
    would point the library at the wrong place silently rather than failing loudly when
    configuration is missing.
    """

    model_config = ConfigDict(frozen=True)

    module_source_directory: Path
    library_root: Path
    database_path: Path | None = None
    cloud_artifact_directory: Path | None = None
    minimum_sample_frames: int = DEFAULT_MINIMUM_SAMPLE_FRAMES

    @property
    def resolved_database_path(self) -> Path:
        """Where the DuckDB catalog lives, defaulting to a fixed filename under the library root."""
        return self.database_path or self.library_root / DEFAULT_DATABASE_FILENAME

    @property
    def resolved_cloud_artifact_directory(self) -> Path:
        """Where cloud-embedding artifacts live, defaulting to a fixed directory under the library root."""
        return self.cloud_artifact_directory or self.library_root / DEFAULT_CLOUD_ARTIFACT_DIRECTORY_NAME


def load_config(path: Path | None = None) -> LibraryConfig:
    """Load and validate the local library configuration.

    The lookup order is an explicit ``path``, then the ``SAMPLELIBRARY_CONFIG`` environment
    variable, then ``config.toml`` at the repository root — the first of these that is actually
    provided wins, so a caller (a test, a CLI flag) can always be explicit about where to read
    from without an environment variable silently overriding it.

    Raises:
        ConfigurationError: no config file exists at the resolved path.
    """
    resolved_path = path or _config_path_from_environment() or DEFAULT_CONFIG_PATH
    if not resolved_path.is_file():
        raise ConfigurationError(
            f"No config file at {resolved_path}. Copy config.example.toml to config.toml and fill in your paths."
        )
    with resolved_path.open("rb") as config_file:
        data = tomllib.load(config_file)
    return LibraryConfig.model_validate(data.get("library", {}))


def _config_path_from_environment() -> Path | None:
    raw_path = os.environ.get(CONFIG_PATH_ENVIRONMENT_VARIABLE)
    return Path(raw_path) if raw_path else None
