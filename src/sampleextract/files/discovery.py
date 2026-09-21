from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from typing import Final

from samplecore.models.sample_file import SampleFileLocation
from samplecore.sample_files.decoding import SAMPLE_FILE_SUFFIXES

HIDDEN_NAME_PREFIX: Final[str] = "."


@dataclass(frozen=True)
class SampleFileDiscovery:
    """The sample files the configured directories hold, beside what the listing could not reach.

    ``missing_directories`` names each configured directory that is not there as a folder, as an
    unmounted drive leaves it, and ``unreadable_directories`` each folder inside one whose listing was
    refused, so a caller deciding anything from what is absent knows which parts went unlisted.
    """

    locations: tuple[SampleFileLocation, ...]
    missing_directories: tuple[Path, ...]
    unreadable_directories: tuple[Path, ...]


def discover_sample_files(directories: tuple[Path, ...], *, exclusions: tuple[str, ...]) -> SampleFileDiscovery:
    """Every sample file the configured directories hold, in location order.

    A file counts when its suffix names a format the library decodes and its name is visible; the
    dot-prefixed names a system keeps beside a file, such as the resource forks macOS writes, stay
    out, and so do dot-prefixed folders. Each path relative to its directory is held against the
    exclusions (see ``is_excluded``), and an excluded folder is left unwalked. Folders reached through
    a symbolic link are walked like any other, and a folder reached a second time is walked once.
    """
    locations: list[SampleFileLocation] = []
    missing: list[Path] = []
    unreadable: list[Path] = []
    walked: set[tuple[int, int]] = set()
    for directory in directories:
        if not directory.is_dir():
            missing.append(directory)
            continue
        for folder, subfolders, files in directory.walk(
            follow_symlinks=True, on_error=lambda error: unreadable.append(Path(str(error.filename)))
        ):
            status = folder.stat()
            identity = (status.st_dev, status.st_ino)
            if identity in walked:
                subfolders.clear()
                continue
            walked.add(identity)
            relative_folder = PurePosixPath(folder.relative_to(directory).as_posix())
            subfolders[:] = [name for name in subfolders if _is_listed(relative_folder / name, exclusions=exclusions)]
            locations.extend(
                SampleFileLocation(directory=directory, relative_path=(relative_folder / name).as_posix())
                for name in files
                if Path(name).suffix.lower() in SAMPLE_FILE_SUFFIXES
                and _is_listed(relative_folder / name, exclusions=exclusions)
                and (folder / name).is_file()
            )

    return SampleFileDiscovery(
        locations=tuple(sorted(locations, key=lambda location: location.sort_key)),
        missing_directories=tuple(missing),
        unreadable_directories=tuple(sorted(unreadable)),
    )


def is_excluded(relative_path: str, *, exclusions: tuple[str, ...]) -> bool:
    """Whether a path relative to its sample directory matches any exclusion.

    Patterns follow shell wildcards, where ``*`` also crosses folders, and match without regard to
    case, since sample packs spell one folder name as "Loops" in one volume and "LOOPS" in the next.
    """
    folded = relative_path.casefold()
    return any(fnmatchcase(folded, pattern.casefold()) for pattern in exclusions)


def _is_listed(relative_path: PurePosixPath, *, exclusions: tuple[str, ...]) -> bool:
    return not relative_path.name.startswith(HIDDEN_NAME_PREFIX) and not is_excluded(
        relative_path.as_posix(), exclusions=exclusions
    )
