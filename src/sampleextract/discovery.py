from __future__ import annotations

from pathlib import Path
from typing import Final

from samplecore.models.tracker import TrackerFormat

FORMAT_LOADERS: Final[dict[str, TrackerFormat]] = {
    ".xm": TrackerFormat.XM,
    ".it": TrackerFormat.IT,
}


def discover_modules(module_source_directory: Path) -> tuple[Path, ...]:
    """Every file under the source directory this library can read, sorted for a stable run order."""
    return tuple(
        sorted(
            path
            for path in module_source_directory.rglob("*")
            if path.is_file() and path.suffix.lower() in FORMAT_LOADERS
        )
    )
