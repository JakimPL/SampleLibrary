from __future__ import annotations

from pathlib import Path

from samplecore.paths import FRONTEND_BUILD_DIRECTORY
from samplelibrary.paths import PACKAGED_FRONTEND_DIRECTORY
from sampleserver.frontend import INDEX_DOCUMENT


def bundled_frontend() -> Path | None:
    """The built frontend the application serves: the one packaged with it, or a source checkout's latest build."""
    for directory in (PACKAGED_FRONTEND_DIRECTORY, FRONTEND_BUILD_DIRECTORY):
        if (directory / INDEX_DOCUMENT).is_file():
            return directory
    return None
