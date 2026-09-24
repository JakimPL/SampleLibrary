from __future__ import annotations

from pathlib import Path
from typing import Final

from samplecore.config import SOURCE_ROOT
from sampleserver.frontend import INDEX_DOCUMENT

PACKAGED_FRONTEND_DIRECTORY: Final[Path] = Path(__file__).resolve().parent / "frontend"
SOURCE_FRONTEND_DIRECTORY: Final[Path] = SOURCE_ROOT / "frontend" / "dist"


def bundled_frontend() -> Path | None:
    """The built frontend the application serves: the one packaged with it, or a source checkout's latest build."""
    for directory in (PACKAGED_FRONTEND_DIRECTORY, SOURCE_FRONTEND_DIRECTORY):
        if (directory / INDEX_DOCUMENT).is_file():
            return directory
    return None
