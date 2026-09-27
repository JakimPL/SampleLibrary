from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path
from typing import Final

from build_app import APP_NAME
from installers.common import copy_program, release_name
from installers.icons import macos_icon
from paths import MACOS_LAUNCHER

PLATFORM: Final[str] = "macos-arm64"
BUNDLE_IDENTIFIER: Final[str] = "io.github.jakimpl.samplelibrary"
MINIMUM_SYSTEM_VERSION: Final[str] = "11.0"
APPLICATIONS_FOLDER: Final[Path] = Path("/Applications")
AD_HOC_IDENTITY: Final[str] = "-"


def macos_disk_image(executable: Path, *, version: str, output_directory: Path, work: Path) -> Path:
    """A disk image holding SampleRipper.app beside a link to Applications, for dragging the app across.

    The bundle's executable is a launcher script. It starts the PyApp executable beside it with its
    output in the person's log folder, and tells them the first start takes a few minutes. The bundle
    carries an ad hoc signature, which Apple silicon requires of every program.
    """
    staging = work / "image"
    bundle = _bundle(executable, version=version, root=staging)
    subprocess.run(["codesign", "--force", "--deep", "--sign", AD_HOC_IDENTITY, bundle], check=True)
    (staging / APPLICATIONS_FOLDER.name).symlink_to(APPLICATIONS_FOLDER)
    target = output_directory / f"{release_name(version, PLATFORM)}.dmg"
    subprocess.run(
        ["hdiutil", "create", "-volname", APP_NAME, "-srcfolder", staging, "-ov", "-format", "UDZO", target],
        check=True,
    )
    return target


def _bundle(executable: Path, *, version: str, root: Path) -> Path:
    bundle = root / f"{APP_NAME}.app"
    contents = bundle / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    (contents / "Resources").mkdir()
    copy_program(MACOS_LAUNCHER, contents / "MacOS" / MACOS_LAUNCHER.name)
    copy_program(executable, contents / "MacOS" / APP_NAME)
    macos_icon(contents / "Resources" / f"{APP_NAME}.icns")
    with (contents / "Info.plist").open("wb") as file:
        plistlib.dump(_bundle_information(version), file)
    return bundle


def _bundle_information(version: str) -> dict[str, str | bool]:
    """The bundle's Info.plist: the launcher runs as a background element, since the application lives in the browser."""
    return {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": BUNDLE_IDENTIFIER,
        "CFBundleVersion": version,
        "CFBundleShortVersionString": version,
        "CFBundleExecutable": MACOS_LAUNCHER.name,
        "CFBundleIconFile": APP_NAME,
        "CFBundlePackageType": "APPL",
        "LSMinimumSystemVersion": MINIMUM_SYSTEM_VERSION,
        "LSUIElement": True,
    }
