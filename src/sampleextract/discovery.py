from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from samplecore.models.tracker import TrackerFormat

FORMAT_LOADERS: Final[dict[str, TrackerFormat]] = {
    ".xm": TrackerFormat.XM,
    ".it": TrackerFormat.IT,
    ".mod": TrackerFormat.MOD,
    ".s3m": TrackerFormat.S3M,
}


@dataclass(frozen=True)
class Discovery:
    """The module files a source directory holds, and the folders inside it that could not be listed."""

    paths: tuple[Path, ...]
    unreadable_directories: tuple[Path, ...]


def discover_modules(module_source_directory: Path) -> Discovery:
    """Every module file under the source directory, sorted for a stable run order.

    Folders reached through a symbolic link are walked like any other, since a collection gathered
    from several drives is often linked together; a folder reached a second time, through a link
    pointing back up the tree, is walked once. A folder the listing is refused for is named in the
    result, so a caller deciding anything from what is absent knows the listing is incomplete.

    Raises:
        FileNotFoundError: the source directory does not exist.
        NotADirectoryError: the source directory names a file.
    """
    if not module_source_directory.exists():
        raise FileNotFoundError(f"the module source directory {module_source_directory} does not exist")
    if not module_source_directory.is_dir():
        raise NotADirectoryError(f"the module source directory {module_source_directory} is a file")

    paths: list[Path] = []
    unreadable: list[Path] = []
    walked: set[tuple[int, int]] = set()
    for directory, subdirectories, files in module_source_directory.walk(
        follow_symlinks=True, on_error=lambda error: unreadable.append(Path(str(error.filename)))
    ):
        status = directory.stat()
        identity = (status.st_dev, status.st_ino)
        if identity in walked:
            subdirectories.clear()
            continue
        walked.add(identity)
        paths.extend(
            directory / name
            for name in files
            if Path(name).suffix.lower() in FORMAT_LOADERS and (directory / name).is_file()
        )

    return Discovery(paths=tuple(sorted(paths)), unreadable_directories=tuple(sorted(unreadable)))
