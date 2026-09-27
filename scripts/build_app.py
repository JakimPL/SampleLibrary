from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from paths import (
    APP_REQUIREMENTS_FILE,
    BIN_DIRECTORY,
    NVIDIA_PINNED_WHEEL_DIRECTORY,
    NVIDIA_REQUIREMENTS_FILE,
    PACKAGE_BUILD_DIRECTORY,
    PINNED_WHEEL_DIRECTORY,
)
from torch_builds import CPU_TORCH_INDEX, CUDA_LOCAL_VERSION, CUDA_TORCH_INDEX, PYPI_INDEX
from wheel_pins import write_pinned_wheel

PYAPP_VERSION: Final[str] = "0.29.0"
PYTHON_VERSION: Final[str] = "3.13"
APP_EXTRA: Final[str] = "app"
APP_MODULE: Final[str] = "sampleripper.app"
APP_NAME: Final[str] = "SampleRipper"
NVIDIA_APP_NAME: Final[str] = f"{APP_NAME}-nvidia"
EXECUTABLE_SUFFIX: Final[str] = ".exe" if sys.platform == "win32" else ""
WHEEL_PATTERN: Final[str] = "sampleripper-*.whl"
# PyTorch publishes CUDA builds for Windows and Linux alone; a Mac computes on its processor.
NVIDIA_PLATFORMS: Final[frozenset[str]] = frozenset({"win32", "linux"})


@dataclass(frozen=True)
class LauncherBuild:
    """One executable the build compiles: its name, the requirements it pins, and the index torch comes from."""

    name: str
    requirements: Path
    pinned_directory: Path
    torch_index: str
    local_version: str | None

    @property
    def executable(self) -> Path:
        return BIN_DIRECTORY / f"{self.name}{EXECUTABLE_SUFFIX}"


PROCESSOR_LAUNCHER: Final[LauncherBuild] = LauncherBuild(
    name=APP_NAME,
    requirements=APP_REQUIREMENTS_FILE,
    pinned_directory=PINNED_WHEEL_DIRECTORY,
    torch_index=CPU_TORCH_INDEX,
    local_version=None,
)
NVIDIA_LAUNCHER: Final[LauncherBuild] = LauncherBuild(
    name=NVIDIA_APP_NAME,
    requirements=NVIDIA_REQUIREMENTS_FILE,
    pinned_directory=NVIDIA_PINNED_WHEEL_DIRECTORY,
    torch_index=CUDA_TORCH_INDEX,
    local_version=CUDA_LOCAL_VERSION,
)


def launcher_builds() -> tuple[LauncherBuild, ...]:
    """The launchers this system ships: the processor one everywhere, and the NVIDIA one where PyTorch builds for CUDA."""
    return (PROCESSOR_LAUNCHER, NVIDIA_LAUNCHER) if sys.platform in NVIDIA_PLATFORMS else (PROCESSOR_LAUNCHER,)


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the SampleRipper executables for this system with PyApp.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Compile PyApp around each pinned wheel: on first run it installs Python and the app with uv, then starts the app.

    Raises:
        SystemExit: cargo is not installed, or `just package` has not built the wheel.
    """
    _parse_arguments(argv)
    cargo = shutil.which("cargo")
    if cargo is None:
        sys.exit("cargo isn't installed. Install Rust with rustup first: https://rustup.rs")
    wheel = _built_wheel()
    BIN_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for launcher in launcher_builds():
        _build_launcher(cargo, wheel, launcher)
        print(f"Built {launcher.executable}.")


def _build_launcher(cargo: str, wheel: Path, launcher: LauncherBuild) -> None:
    pinned = write_pinned_wheel(
        wheel, launcher.requirements, launcher.pinned_directory, local_version=launcher.local_version
    )
    with tempfile.TemporaryDirectory() as build_root:
        subprocess.run(
            [cargo, "install", "pyapp", "--version", PYAPP_VERSION, "--force", "--root", build_root],
            check=True,
            env={**os.environ, **_pyapp_settings(pinned.resolve(), torch_index=launcher.torch_index)},
        )
        shutil.copy2(Path(build_root) / "bin" / f"pyapp{EXECUTABLE_SUFFIX}", launcher.executable)


def _built_wheel() -> Path:
    """The sampleripper wheel `just package` built.

    Raises:
        SystemExit: the package folder holds none, or more than one, or a launcher's requirements are missing.
    """
    wheels = sorted(PACKAGE_BUILD_DIRECTORY.glob(WHEEL_PATTERN))
    requirements_written = all(launcher.requirements.is_file() for launcher in launcher_builds())
    if len(wheels) != 1 or not requirements_written:
        sys.exit(f"No single sampleripper wheel in {PACKAGE_BUILD_DIRECTORY}. Run `just package` first.")
    return wheels[0]


def _pyapp_settings(wheel: Path, *, torch_index: str) -> dict[str, str]:
    """What PyApp embeds: the wheel and its app extra, the Python it installs, and the index uv takes torch from.

    uv consults every index for each package under `unsafe-best-match`, and takes a version several
    indexes serve from the first of them. PyPI comes first, so every package it serves downloads
    from its own servers, and torch's CUDA or processor build, which PyPI lacks, from PyTorch's
    index. PyTorch's index links the NVIDIA libraries to NVIDIA's own server, which PyPI's copies
    of the same files spare the first start. As a GUI, the application runs in a process of its own
    once installed, windowless through pythonw on Windows; the first start shows the installation's
    progress in a console.
    """
    installer_arguments = [
        "--index-strategy",
        "unsafe-best-match",
        "--extra-index-url",
        PYPI_INDEX,
        "--extra-index-url",
        torch_index,
    ]
    return {
        "PYAPP_PROJECT_PATH": str(wheel),
        "PYAPP_PROJECT_FEATURES": APP_EXTRA,
        "PYAPP_EXEC_MODULE": APP_MODULE,
        "PYAPP_PYTHON_VERSION": PYTHON_VERSION,
        "PYAPP_UV_ENABLED": "1",
        "PYAPP_IS_GUI": "1",
        "PYAPP_PIP_EXTRA_ARGS": " ".join(installer_arguments),
    }


if __name__ == "__main__":
    main()
