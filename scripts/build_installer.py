from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from build_app import NVIDIA_LAUNCHER, PROCESSOR_LAUNCHER, launcher_builds
from installers.linux import linux_appimage
from installers.macos import macos_disk_image
from installers.windows import windows_installer
from paths import DIST_DIRECTORY, PROJECT_FILE
from versions import project_version


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wrap the SampleLibrary executable into this system's installer.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Wrap the executables `just executable` built into the file people download for this system.

    Windows gets an Inno Setup installer, macOS a disk image holding the app bundle, and Linux an
    AppImage, each named after the project's version and the platform. The Windows installer and the
    AppImage carry the NVIDIA launcher beside the processor one and pick one of them on the person's
    machine.

    Raises:
        SystemExit: `just executable` has not built every launcher.
    """
    _parse_arguments(argv)
    for launcher in launcher_builds():
        if not launcher.executable.is_file():
            sys.exit(f"No executable at {launcher.executable}. Run `just executable` first.")
    version = project_version(PROJECT_FILE)
    DIST_DIRECTORY.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        installer = _build(version=version, output_directory=DIST_DIRECTORY, work=Path(work))
    print(f"Built {installer}.")


def _build(*, version: str, output_directory: Path, work: Path) -> Path:
    processor = PROCESSOR_LAUNCHER.executable
    nvidia = NVIDIA_LAUNCHER.executable
    match sys.platform:
        case "win32":
            return windows_installer(
                processor, nvidia_executable=nvidia, version=version, output_directory=output_directory, work=work
            )
        case "darwin":
            return macos_disk_image(processor, version=version, output_directory=output_directory, work=work)
        case _:
            return linux_appimage(
                processor, nvidia_executable=nvidia, version=version, output_directory=output_directory, work=work
            )


if __name__ == "__main__":
    main()
