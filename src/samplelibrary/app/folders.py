from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Final

from platformdirs import user_desktop_path, user_documents_path, user_downloads_path, user_music_path
from pydantic import BaseModel

from samplecore.models.base import FROZEN
from samplecore.sample_files.decoding import SAMPLE_FILE_SUFFIXES
from sampleextract.discovery import FORMAT_LOADERS

HIDDEN_PREFIX: Final[str] = "."
MOUNT_DIRECTORIES: Final[tuple[Path, ...]] = (Path("/Volumes"), Path("/media"), Path("/mnt"), Path("/run/media"))
FILESYSTEM_ROOT: Final[Path] = Path("/")


class FolderUnreadableError(Exception):
    """Raised when a folder a person opens in the folder browser cannot be listed."""


class Place(BaseModel):
    """A folder the folder browser offers as a starting point: a person's own folders, and every drive."""

    model_config = FROZEN

    name: str
    path: str


class Folder(BaseModel):
    model_config = FROZEN

    name: str
    path: str


class FolderListing(BaseModel):
    """One folder as the folder browser shows it: the folders inside it, and how many modules and audio files it holds itself.

    The counts cover the folder's own files, which is what a person needs to recognize a collection
    while the listing stays quick on a large one.
    """

    model_config = FROZEN

    path: str
    parent: str | None
    folders: tuple[Folder, ...]
    module_files: int
    audio_files: int


def places() -> tuple[Place, ...]:
    """The person's home and media folders that exist, followed by every drive or mounted volume."""
    candidates = (
        ("Home", Path.home()),
        ("Music", user_music_path()),
        ("Downloads", user_downloads_path()),
        ("Documents", user_documents_path()),
        ("Desktop", user_desktop_path()),
    )
    own = tuple(Place(name=name, path=str(path)) for name, path in candidates if path.is_dir())
    return own + tuple(Place(name=str(root), path=str(root)) for root in _roots())


def list_folder(path: Path) -> FolderListing:
    """The folders inside ``path`` in name order, hidden ones left out, with the folder's own file counts.

    Raises:
        FolderUnreadableError: the path names no folder, or the system refuses to list it.
    """
    folder = path.expanduser().resolve()
    if not folder.is_dir():
        raise FolderUnreadableError(f"{folder} is no folder")
    try:
        entries = sorted(_visible_entries(folder), key=lambda entry: entry.name.casefold())
    except OSError as error:
        raise FolderUnreadableError(f"{folder} cannot be opened: {error.strerror}") from error
    files = [entry for entry in entries if entry.is_file()]
    return FolderListing(
        path=str(folder),
        parent=str(folder.parent) if folder.parent != folder else None,
        folders=tuple(Folder(name=entry.name, path=str(entry)) for entry in entries if _is_folder(entry)),
        module_files=sum(1 for entry in files if entry.suffix.lower() in FORMAT_LOADERS),
        audio_files=sum(1 for entry in files if entry.suffix.lower() in SAMPLE_FILE_SUFFIXES),
    )


def _visible_entries(folder: Path) -> Iterator[Path]:
    return (entry for entry in folder.iterdir() if not entry.name.startswith(HIDDEN_PREFIX))


def _is_folder(entry: Path) -> bool:
    try:
        return entry.is_dir()
    except OSError:
        return False


def _roots() -> tuple[Path, ...]:
    """Every drive on Windows; the filesystem root and the folders volumes mount under elsewhere."""
    if sys.platform == "win32":
        return tuple(Path(drive) for drive in os.listdrives())  # pylint: disable=no-member  # Windows alone has it
    return (FILESYSTEM_ROOT, *(directory for directory in MOUNT_DIRECTORIES if directory.is_dir()))
