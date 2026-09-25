from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

from build_app import APP_NAME
from installers.common import release_name
from installers.icons import windows_icon
from paths import WINDOWS_INSTALLER_SCRIPT, WINDOWS_QUIT_SCRIPT

PLATFORM: Final[str] = "windows-x64"
INNO_SETUP_COMPILER: Final[str] = "ISCC"
INNO_SETUP_DEFAULT: Final[Path] = Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe")
INSTALLER_SUFFIX: Final[str] = "-setup"


def windows_installer(executable: Path, *, version: str, output_directory: Path, work: Path) -> Path:
    """An Inno Setup installer putting the app in the person's own programs folder, with Start menu and desktop shortcuts.

    Installing over an earlier version, and uninstalling, first quit the running application and
    remove the packages the earlier executable installed; the library and its settings stay.

    Raises:
        SystemExit: Inno Setup is not installed.
    """
    output_name = f"{release_name(version, PLATFORM)}{INSTALLER_SUFFIX}"
    subprocess.run(
        [
            _inno_setup_compiler(),
            f"/DVersion={version}",
            f"/DExecutable={executable.resolve()}",
            f"/DIcon={windows_icon(work / f'{APP_NAME}.ico')}",
            f"/DQuitScript={WINDOWS_QUIT_SCRIPT}",
            f"/DOutputDirectory={output_directory.resolve()}",
            f"/DOutputName={output_name}",
            WINDOWS_INSTALLER_SCRIPT,
        ],
        check=True,
    )
    return output_directory / f"{output_name}.exe"


def _inno_setup_compiler() -> Path:
    """Inno Setup's compiler, found on the PATH or in its default folder.

    Raises:
        SystemExit: Inno Setup is neither on the PATH nor in its default folder.
    """
    found = shutil.which(INNO_SETUP_COMPILER)
    if found is not None:
        return Path(found)
    if INNO_SETUP_DEFAULT.is_file():
        return INNO_SETUP_DEFAULT
    sys.exit("Inno Setup isn't installed. Get it from https://jrsoftware.org/isinfo.php.")
