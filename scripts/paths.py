from __future__ import annotations

from pathlib import Path
from typing import Final

REPOSITORY_DIRECTORY: Final[Path] = Path(__file__).resolve().parents[1]
PROJECT_FILE: Final[Path] = REPOSITORY_DIRECTORY / "pyproject.toml"
TRACKMOD_PROJECT_FILE: Final[Path] = REPOSITORY_DIRECTORY / "trackmod" / "pyproject.toml"
DESCRIPTOR_UPLOAD_DIRECTORY: Final[Path] = REPOSITORY_DIRECTORY / "dist" / "descriptor"
APP_ICON: Final[Path] = REPOSITORY_DIRECTORY / "frontend" / "public" / "icons" / "icon-512.png"
PACKAGING_DIRECTORY: Final[Path] = REPOSITORY_DIRECTORY / "packaging"
WINDOWS_INSTALLER_SCRIPT: Final[Path] = PACKAGING_DIRECTORY / "windows" / "SampleLibrary.iss"
WINDOWS_QUIT_SCRIPT: Final[Path] = PACKAGING_DIRECTORY / "windows" / "quit.ps1"
MACOS_LAUNCHER: Final[Path] = PACKAGING_DIRECTORY / "macos" / "launch"
LINUX_APP_RUN: Final[Path] = PACKAGING_DIRECTORY / "linux" / "AppRun"
LINUX_DESKTOP_ENTRY: Final[Path] = PACKAGING_DIRECTORY / "linux" / "SampleLibrary.desktop"
