from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from build_app import APP_NAME, EXECUTABLE_SUFFIX
from installers.linux import linux_appimage
from installers.macos import macos_disk_image
from installers.windows import windows_installer
from paths import PROJECT_FILE
from versions import project_version


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wrap the SampleLibrary executable into this system's installer.")
    parser.add_argument(
        "--dist",
        type=Path,
        required=True,
        help="The folder `just executable` built into; the installer is written there too.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Wrap the executable `just executable` built into the file people download for this system.

    Windows gets an Inno Setup installer, macOS a disk image holding the app bundle, and Linux an
    AppImage, each named after the project's version and the platform.

    Raises:
        SystemExit: the folder holds no built executable.
    """
    arguments = _parse_arguments(argv)
    executable = arguments.dist / f"{APP_NAME}{EXECUTABLE_SUFFIX}"
    if not executable.is_file():
        sys.exit(f"No executable in {arguments.dist}. Run `just executable` first.")
    version = project_version(PROJECT_FILE)
    with tempfile.TemporaryDirectory() as work:
        installer = _build(executable, version=version, output_directory=arguments.dist, work=Path(work))
    print(f"Built {installer}.")


def _build(executable: Path, *, version: str, output_directory: Path, work: Path) -> Path:
    match sys.platform:
        case "win32":
            return windows_installer(executable, version=version, output_directory=output_directory, work=work)
        case "darwin":
            return macos_disk_image(executable, version=version, output_directory=output_directory, work=work)
        case _:
            return linux_appimage(executable, version=version, output_directory=output_directory, work=work)


if __name__ == "__main__":
    main()
