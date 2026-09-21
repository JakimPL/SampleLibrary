from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Final

from pydantic import BaseModel, field_validator
from trackmod.schema.scalars import Rate

from samplecore.models.base import FROZEN
from samplecore.models.scalars import Count, SampleHash

_TRAVERSING_PARTS: Final[frozenset[str]] = frozenset({".", ".."})


class SampleFileLocation(BaseModel):
    """Where a sample file sits: one of the configured sample directories, and its path inside it.

    The path inside the directory is written with forward slashes on every system and names a file
    below the directory, which keeps a location read from a request or a catalog row within the
    directory it names.
    """

    model_config = FROZEN

    directory: Path
    relative_path: str

    @field_validator("directory")
    @classmethod
    def _absolute(cls, directory: Path) -> Path:
        if not directory.is_absolute():
            raise ValueError(f"{directory} must be an absolute path")
        return directory

    @field_validator("relative_path")
    @classmethod
    def _below_the_directory(cls, relative_path: str) -> str:
        posix_path = PurePosixPath(relative_path)
        if (
            not posix_path.parts
            or posix_path.is_absolute()
            or posix_path.as_posix() != relative_path
            or _TRAVERSING_PARTS & set(posix_path.parts)
        ):
            raise ValueError(f"{relative_path!r} must be a forward-slash path below its directory")
        return relative_path

    @classmethod
    def inside(cls, path: Path, directories: Iterable[Path]) -> SampleFileLocation | None:
        """The location of a file inside whichever of ``directories`` holds it.

        ``None`` when the path lies below none of them, or climbs back out of one through ``..``,
        which is how a process reading files a request names keeps to the directories it serves.
        """
        if _TRAVERSING_PARTS & set(path.parts):
            return None
        for directory in directories:
            if path != directory and path.is_relative_to(directory):
                return cls(directory=directory, relative_path=path.relative_to(directory).as_posix())
        return None

    @property
    def path(self) -> Path:
        """The file on this machine."""
        return self.directory.joinpath(*PurePosixPath(self.relative_path).parts)

    @property
    def stem(self) -> str:
        """The file's name without its suffix, which is what a person named the sound."""
        return stem_of(self.relative_path)

    @property
    def sort_key(self) -> tuple[str, str]:
        """The order locations are listed and chosen in, the same on every system."""
        return (self.directory.as_posix(), self.relative_path)


class FileFingerprint(BaseModel):
    """What a file's metadata says about its content: its size and when it was last written.

    A cataloged file whose fingerprint still matches holds the audio it was hashed from, which is
    what lets a rescan pass over it unread and a reader trust it under its hash.
    """

    model_config = FROZEN

    size_bytes: Count
    modified_ns: Count

    @classmethod
    def of(cls, status: os.stat_result) -> FileFingerprint:
        """The fingerprint a file's current status gives."""
        return cls(size_bytes=status.st_size, modified_ns=status.st_mtime_ns)


class SampleFile(BaseModel):
    """One plain audio file holding a sample, read in place from a configured sample directory.

    It is the counterpart of a module occurrence for audio living outside any module: it names the
    sample the file decodes to, the rate the file declares, which is the rate the sample is played
    at, and the fingerprint the file had when it was hashed.
    """

    model_config = FROZEN

    sample_hash: SampleHash
    location: SampleFileLocation
    rate: Rate
    fingerprint: FileFingerprint


def stem_of(relative_path: str) -> str:
    """A sample file's name without its suffix, from its path inside its directory."""
    return PurePosixPath(relative_path).stem
