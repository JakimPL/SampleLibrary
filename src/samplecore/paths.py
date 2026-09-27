from __future__ import annotations

from pathlib import Path
from typing import Final

from platformdirs import user_config_path, user_music_path

APPLICATION_NAME: Final[str] = "SampleRipper"
CONFIG_FILE_NAME: Final[str] = "config.toml"
# The folder holding every package of this project: `src` in a source checkout, `site-packages` in an
# installation. The checkout's paths below name files only where `runs_from_checkout()` holds.
PACKAGES_DIRECTORY: Final[Path] = Path(__file__).resolve().parents[1]
CHECKOUT_DIRECTORY: Final[Path] = PACKAGES_DIRECTORY.parent
CHECKOUT_CONFIG_PATH: Final[Path] = CHECKOUT_DIRECTORY / CONFIG_FILE_NAME
EXAMPLE_CONFIG_PATH: Final[Path] = CHECKOUT_DIRECTORY / "config.example.toml"
FRONTEND_BUILD_DIRECTORY: Final[Path] = CHECKOUT_DIRECTORY / "build" / "frontend"


def runs_from_checkout() -> bool:
    """Whether this code runs from a source checkout, recognized by the example config committed beside `src`."""
    return EXAMPLE_CONFIG_PATH.is_file()


def user_config_file() -> Path:
    """The config file an installed application keeps in the system's settings folder for the user."""
    return user_config_path(APPLICATION_NAME, appauthor=False) / CONFIG_FILE_NAME


def default_library_root() -> Path:
    """The library root the application suggests to a person choosing one: a folder in their music folder."""
    return user_music_path() / APPLICATION_NAME
