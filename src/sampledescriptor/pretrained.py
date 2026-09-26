from __future__ import annotations

import hashlib
import tomllib
import urllib.error
import urllib.request
from pathlib import Path
from typing import IO, Final

import tomlkit
from pydantic import BaseModel, Field

from samplecore.models.base import FROZEN
from samplecore.progress import ProgressBar
from samplecore.storage.atomic import write_atomically, write_bytes_atomically
from sampledescriptor.geometry import Anchor
from sampledescriptor.paths import PRETRAINED_RELEASE_PATH

SHA256_PATTERN: Final[str] = r"^[0-9a-f]{64}$"
DOWNLOAD_CHUNK_BYTES: Final[int] = 1 << 20
DOWNLOAD_TIMEOUT_SECONDS: Final[float] = 60.0
DOWNLOAD_LABEL: Final[str] = "Downloading the descriptor"
MISSING_RELEASE_MESSAGE: Final[str] = "This version of SampleLibrary carries no descriptor to download."


class PretrainedDescriptorMissingError(Exception):
    """Raised when a library asks for the pretrained descriptor and none is published for this version."""


class PretrainedDownloadError(Exception):
    """Raised when the pretrained descriptor fails to download, or the download differs from its release."""


class PretrainedGrid(BaseModel):
    """What the grid cache must be read under for the pretrained descriptor to describe it."""

    model_config = FROZEN

    canonicalizer: str
    anchor: Anchor
    bands_per_semitone: int = Field(ge=1)


class PretrainedRelease(BaseModel):
    """The published descriptor new libraries take: where it downloads from, the digest of its bytes, and its grid.

    The record is committed with the code that reads it, so the pipeline plans a library's build,
    naming its outputs by the digest, before anything is downloaded.
    """

    model_config = FROZEN

    url: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    grid: PretrainedGrid


def publishes_pretrained() -> bool:
    """Whether this version of the application carries a published descriptor for libraries to download."""
    return PRETRAINED_RELEASE_PATH.is_file()


def pretrained_release() -> PretrainedRelease:
    """The descriptor this version of the application takes.

    Raises:
        PretrainedDescriptorMissingError: no descriptor is published for this version.
    """
    return read_pretrained_release(PRETRAINED_RELEASE_PATH)


def read_pretrained_release(path: Path) -> PretrainedRelease:
    """The release record at ``path``.

    Raises:
        PretrainedDescriptorMissingError: no record is written there.
    """
    if not path.is_file():
        raise PretrainedDescriptorMissingError(MISSING_RELEASE_MESSAGE)
    with path.open("rb") as file:
        return PretrainedRelease.model_validate(tomllib.load(file))


def write_pretrained_release(release: PretrainedRelease, path: Path) -> None:
    write_bytes_atomically(path, tomlkit.dumps(release.model_dump(mode="json")).encode("utf-8"))


def download_pretrained(release: PretrainedRelease, target: Path) -> None:
    """Download the published descriptor to ``target``, kept only when its bytes match the release's digest.

    The download reports its progress the way every pass of the pipeline does, so the application
    shows it while a build runs.

    Raises:
        PretrainedDownloadError: the download failed, or its bytes differ from the release.
    """
    digest = hashlib.sha256()

    def write(file: IO[bytes]) -> None:
        with urllib.request.urlopen(release.url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            total = int(response.headers.get("Content-Length", 0))
            with ProgressBar(total=total, label=DOWNLOAD_LABEL) as progress:
                while chunk := response.read(DOWNLOAD_CHUNK_BYTES):
                    file.write(chunk)
                    digest.update(chunk)
                    progress.update(len(chunk))
        if digest.hexdigest() != release.sha256:
            raise PretrainedDownloadError(f"The descriptor downloaded from {release.url} doesn't match its release.")

    try:
        write_atomically(target, write)
    except urllib.error.URLError as error:
        raise PretrainedDownloadError(f"Couldn't download the descriptor from {release.url}: {error.reason}") from error
