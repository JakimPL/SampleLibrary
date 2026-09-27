from __future__ import annotations

from pathlib import Path
from typing import Final

REPOSITORY_DIRECTORY: Final[Path] = Path(__file__).resolve().parents[1]
PROJECT_FILE: Final[Path] = REPOSITORY_DIRECTORY / "pyproject.toml"
FRONTEND_DIRECTORY: Final[Path] = REPOSITORY_DIRECTORY / "frontend"
APP_ICON: Final[Path] = FRONTEND_DIRECTORY / "public" / "icons" / "icon-512.png"
PACKAGING_DIRECTORY: Final[Path] = REPOSITORY_DIRECTORY / "packaging"
WINDOWS_INSTALLER_SCRIPT: Final[Path] = PACKAGING_DIRECTORY / "windows" / "SampleRipper.iss"
WINDOWS_QUIT_SCRIPT: Final[Path] = PACKAGING_DIRECTORY / "windows" / "quit.ps1"
MACOS_LAUNCHER: Final[Path] = PACKAGING_DIRECTORY / "macos" / "launch"
LINUX_APP_RUN: Final[Path] = PACKAGING_DIRECTORY / "linux" / "AppRun"
LINUX_DESKTOP_ENTRY: Final[Path] = PACKAGING_DIRECTORY / "linux" / "SampleRipper.desktop"
DOCKER_DIRECTORY: Final[Path] = REPOSITORY_DIRECTORY / "docker"
POSTGRES_ENVIRONMENT_FILE: Final[Path] = DOCKER_DIRECTORY / "postgres.env"
SITE_ENVIRONMENT_FILE: Final[Path] = DOCKER_DIRECTORY / "site.env"

BUILD_DIRECTORY: Final[Path] = REPOSITORY_DIRECTORY / "build"
PACKAGE_BUILD_DIRECTORY: Final[Path] = BUILD_DIRECTORY / "package"
PINNED_WHEEL_DIRECTORY: Final[Path] = PACKAGE_BUILD_DIRECTORY / "pinned"
APP_REQUIREMENTS_FILE: Final[Path] = PACKAGE_BUILD_DIRECTORY / "app-requirements.txt"
NVIDIA_PINNED_WHEEL_DIRECTORY: Final[Path] = PACKAGE_BUILD_DIRECTORY / "pinned-nvidia"
NVIDIA_REQUIREMENTS_FILE: Final[Path] = PACKAGE_BUILD_DIRECTORY / "app-requirements-nvidia.txt"
BIN_DIRECTORY: Final[Path] = REPOSITORY_DIRECTORY / "bin"
DIST_DIRECTORY: Final[Path] = REPOSITORY_DIRECTORY / "dist"
DESCRIPTOR_UPLOAD_DIRECTORY: Final[Path] = DIST_DIRECTORY / "descriptor"
