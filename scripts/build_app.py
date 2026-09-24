from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Final

from wheel_pins import write_pinned_wheel

PYAPP_VERSION: Final[str] = "0.29.0"
PYTHON_VERSION: Final[str] = "3.13"
APP_EXTRA: Final[str] = "app"
APP_MODULE: Final[str] = "samplelibrary.app"
APP_NAME: Final[str] = "SampleLibrary"
CPU_TORCH_INDEX: Final[str] = "https://download.pytorch.org/whl/cpu"
EXECUTABLE_SUFFIX: Final[str] = ".exe" if sys.platform == "win32" else ""
REQUIREMENTS_NAME: Final[str] = "app-requirements.txt"
PINNED_DIRECTORY_NAME: Final[str] = "app"
WHEEL_PATTERN: Final[str] = "samplelibrary-*.whl"


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the SampleLibrary executable for this system with PyApp.")
    parser.add_argument(
        "--dist",
        type=Path,
        required=True,
        help="The folder `just package` filled; the executable is written there too.",
    )
    parser.add_argument(
        "--find-links",
        type=Path,
        default=None,
        help="A folder of wheels the first run may install from, for trying a build before its packages are published.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Compile PyApp around the pinned wheel: on first run it installs Python and the app with uv, then starts the app.

    Raises:
        SystemExit: cargo is not installed, or the folder holds no single samplelibrary wheel.
    """
    arguments = _parse_arguments(argv)
    cargo = shutil.which("cargo")
    if cargo is None:
        sys.exit("cargo is not installed. Install Rust with rustup first.")
    wheel = write_pinned_wheel(
        _built_wheel(arguments.dist), arguments.dist / REQUIREMENTS_NAME, arguments.dist / PINNED_DIRECTORY_NAME
    )
    with tempfile.TemporaryDirectory() as build_root:
        subprocess.run(
            [cargo, "install", "pyapp", "--version", PYAPP_VERSION, "--force", "--root", build_root],
            check=True,
            env={**os.environ, **_pyapp_settings(wheel.resolve(), arguments.find_links)},
        )
        executable = arguments.dist / f"{APP_NAME}{EXECUTABLE_SUFFIX}"
        shutil.copy2(Path(build_root) / "bin" / f"pyapp{EXECUTABLE_SUFFIX}", executable)
    print(f"Built {executable}.")


def _built_wheel(dist: Path) -> Path:
    """The samplelibrary wheel `just package` built.

    Raises:
        SystemExit: the folder holds none, or more than one.
    """
    wheels = sorted(dist.glob(WHEEL_PATTERN))
    if len(wheels) != 1:
        sys.exit(f"Expected one samplelibrary wheel in {dist}, found {len(wheels)}. Run `just package` first.")
    return wheels[0]


def _pyapp_settings(wheel: Path, find_links: Path | None) -> dict[str, str]:
    """What PyApp embeds: the wheel and its app extra, the Python it installs, and how uv reaches CPU torch.

    uv consults every index for each package under `unsafe-best-match`, which is what lets torch come
    from PyTorch's processor index while everything else comes from PyPI.
    """
    installer_arguments = ["--index-strategy", "unsafe-best-match", "--extra-index-url", CPU_TORCH_INDEX]
    if find_links is not None:
        installer_arguments += ["--find-links", str(find_links.resolve())]
    return {
        "PYAPP_PROJECT_PATH": str(wheel),
        "PYAPP_PROJECT_FEATURES": APP_EXTRA,
        "PYAPP_EXEC_MODULE": APP_MODULE,
        "PYAPP_PYTHON_VERSION": PYTHON_VERSION,
        "PYAPP_UV_ENABLED": "1",
        "PYAPP_PIP_EXTRA_ARGS": " ".join(installer_arguments),
    }


if __name__ == "__main__":
    main()
