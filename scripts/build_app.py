from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Final

from paths import APP_REQUIREMENTS_FILE, BIN_DIRECTORY, PACKAGE_BUILD_DIRECTORY, PINNED_WHEEL_DIRECTORY
from wheel_pins import write_pinned_wheel

PYAPP_VERSION: Final[str] = "0.29.0"
PYTHON_VERSION: Final[str] = "3.13"
APP_EXTRA: Final[str] = "app"
APP_MODULE: Final[str] = "samplelibrary.app"
APP_NAME: Final[str] = "SampleLibrary"
CPU_TORCH_INDEX: Final[str] = "https://download.pytorch.org/whl/cpu"
EXECUTABLE_SUFFIX: Final[str] = ".exe" if sys.platform == "win32" else ""
WHEEL_PATTERN: Final[str] = "samplelibrary-*.whl"


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the SampleLibrary executable for this system with PyApp.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Compile PyApp around the pinned wheel: on first run it installs Python and the app with uv, then starts the app.

    Raises:
        SystemExit: cargo is not installed, or `just package` has not built the wheel.
    """
    _parse_arguments(argv)
    cargo = shutil.which("cargo")
    if cargo is None:
        sys.exit("cargo isn't installed. Install Rust with rustup first: https://rustup.rs")
    wheel = write_pinned_wheel(_built_wheel(), APP_REQUIREMENTS_FILE, PINNED_WHEEL_DIRECTORY)
    BIN_DIRECTORY.mkdir(parents=True, exist_ok=True)
    executable = BIN_DIRECTORY / f"{APP_NAME}{EXECUTABLE_SUFFIX}"
    with tempfile.TemporaryDirectory() as build_root:
        subprocess.run(
            [cargo, "install", "pyapp", "--version", PYAPP_VERSION, "--force", "--root", build_root],
            check=True,
            env={**os.environ, **_pyapp_settings(wheel.resolve())},
        )
        shutil.copy2(Path(build_root) / "bin" / f"pyapp{EXECUTABLE_SUFFIX}", executable)
    print(f"Built {executable}.")


def _built_wheel() -> Path:
    """The samplelibrary wheel `just package` built.

    Raises:
        SystemExit: the package folder holds none, or more than one.
    """
    wheels = sorted(PACKAGE_BUILD_DIRECTORY.glob(WHEEL_PATTERN))
    if len(wheels) != 1 or not APP_REQUIREMENTS_FILE.is_file():
        sys.exit(f"No single samplelibrary wheel in {PACKAGE_BUILD_DIRECTORY}. Run `just package` first.")
    return wheels[0]


def _pyapp_settings(wheel: Path) -> dict[str, str]:
    """What PyApp embeds: the wheel and its app extra, the Python it installs, and how uv reaches CPU torch.

    uv consults every index for each package under `unsafe-best-match`, which is what lets torch come
    from PyTorch's processor index while everything else comes from PyPI. As a GUI, the application
    runs in a process of its own once installed, windowless through pythonw on Windows; the first
    start shows the installation's progress in a console.
    """
    installer_arguments = ["--index-strategy", "unsafe-best-match", "--extra-index-url", CPU_TORCH_INDEX]
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
