from __future__ import annotations

import os
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Final

from build_app import APP_NAME
from installers.common import PROGRAM_MODE, copy_program, release_name
from installers.icons import linux_icon
from paths import LINUX_APP_RUN, LINUX_DESKTOP_ENTRY

PLATFORM: Final[str] = "linux-x64"
ARCHITECTURE: Final[str] = "x86_64"
DESKTOP_ICON_NAME: Final[str] = "samplelibrary.png"
APPIMAGETOOL_URL: Final[str] = (
    "https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage"
)
DOWNLOAD_TIMEOUT_SECONDS: Final[float] = 120.0


def linux_appimage(executable: Path, *, version: str, output_directory: Path, work: Path) -> Path:
    """An AppImage: one file that runs on most distributions, which desktop tools add to the menu by its entry.

    Its AppRun starts the PyApp executable inside with its output in the person's state folder, and
    tells them the first start takes a few minutes. The icon's name matches the entry's `Icon` key.
    """
    app_directory = work / f"{APP_NAME}.AppDir"
    programs = app_directory / "usr" / "bin"
    programs.mkdir(parents=True)
    copy_program(LINUX_APP_RUN, app_directory / LINUX_APP_RUN.name)
    copy_program(executable, programs / APP_NAME)
    shutil.copy2(LINUX_DESKTOP_ENTRY, app_directory / LINUX_DESKTOP_ENTRY.name)
    linux_icon(app_directory / DESKTOP_ICON_NAME)
    target = output_directory / f"{release_name(version, PLATFORM)}.AppImage"
    subprocess.run(
        [_appimagetool(work), app_directory, target],
        check=True,
        env={**os.environ, "ARCH": ARCHITECTURE, "APPIMAGE_EXTRACT_AND_RUN": "1"},
    )
    return target


def _appimagetool(work: Path) -> Path:
    """appimagetool at its pinned release, run extracted, which works on every build machine, FUSE or not."""
    tool = work / "appimagetool"
    with urllib.request.urlopen(APPIMAGETOOL_URL, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        tool.write_bytes(response.read())
    tool.chmod(PROGRAM_MODE)
    return tool
