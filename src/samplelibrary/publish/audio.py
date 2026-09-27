from __future__ import annotations

import errno
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from samplecore.models.sample_file import SampleFile
from samplecore.progress import ProgressBar
from samplecore.storage import audio_store
from samplecore.storage.atomic import copy_atomically, write_bytes_atomically
from samplecore.storage.sample_audio import SampleAudio, SampleUnavailableError

AUDIO_TREE_LABEL: Final[str] = "Gathering the site's audio"
WAV_SUFFIX: Final[str] = ".wav"

_logger = logging.getLogger(__name__)


class MissingObjectsError(Exception):
    """Raised when samples a module holds have no stored object, which a store only lacks once damaged."""

    def __init__(self, sample_hashes: tuple[str, ...]) -> None:
        super().__init__(f"{len(sample_hashes)} samples have no stored object")
        self.sample_hashes = sample_hashes


@dataclass(frozen=True)
class PublishedAudio:
    """What building a site's audio store did, and the file-only samples it left out for want of a readable file."""

    files: int
    stored_bytes: int
    written: int
    removed: int
    unreadable: tuple[str, ...]


def build_audio_tree(
    library_root: Path,
    tree: Path,
    *,
    module_samples: frozenset[str],
    file_samples: Mapping[str, tuple[SampleFile, ...]],
) -> PublishedAudio:
    """Hold, in ``tree``, the stored audio of every sample a site serves, laid out as the library's own store.

    A sample a module holds is linked from the library's store, which costs no space on the same
    file system and a copy on another. A sample found only in a published directory is written as
    the store would hold it, read from the first of its files that still reads as it was scanned;
    one none of whose files does is left out and named. Anything else in ``tree`` goes, so the
    folder uploaded holds the samples published and no other. The site then reads every sample from
    its own store, whichever file it was once found in.

    Raises:
        MissingObjectsError: a sample a module holds has no stored object, before ``tree`` changes.
    """
    missing = tuple(
        sorted(sample_hash for sample_hash in module_samples if not _stored(library_root, sample_hash).is_file())
    )
    if missing:
        raise MissingObjectsError(missing)
    written = 0
    unreadable: list[str] = []
    with ProgressBar(total=len(module_samples) + len(file_samples), label=AUDIO_TREE_LABEL) as progress:
        for sample_hash in sorted(module_samples):
            written += _link(_stored(library_root, sample_hash), _stored(tree, sample_hash))
            progress.update(1)
        for sample_hash, found in sorted(file_samples.items()):
            if _stored(library_root, sample_hash).is_file():
                written += _link(_stored(library_root, sample_hash), _stored(tree, sample_hash))
            elif not _stored(tree, sample_hash).is_file():
                if _write_from_files(library_root, tree, sample_hash, found):
                    written += 1
                else:
                    unreadable.append(sample_hash)
            progress.update(1)
    kept = (module_samples | frozenset(file_samples)) - frozenset(unreadable)
    removed = _remove_all_but(tree, kept)
    files = _stored_files(tree)
    return PublishedAudio(
        files=len(files),
        stored_bytes=sum(path.stat().st_size for path in files),
        written=written,
        removed=removed,
        unreadable=tuple(unreadable),
    )


def _stored(root: Path, sample_hash: str) -> Path:
    return audio_store.object_path(root, sample_hash)


def _link(source: Path, destination: Path) -> int:
    """Put the stored object at ``destination`` as a link to ``source``, or a copy across file systems; 1 once placed."""
    if destination.is_file():
        return 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise
        copy_atomically(source, destination)
    return 1


def _write_from_files(library_root: Path, tree: Path, sample_hash: str, found: tuple[SampleFile, ...]) -> bool:
    """Write a file-only sample as the store would hold it, reporting whether one of its files still read as scanned."""
    try:
        sample_pcm = SampleAudio.of_files(library_root, found).read_by_hash(sample_hash)
    except SampleUnavailableError as error:
        _logger.warning("%s", error)
        return False
    write_bytes_atomically(_stored(tree, sample_hash), audio_store.encode_wav(sample_pcm))
    return True


def _remove_all_but(tree: Path, kept: frozenset[str]) -> int:
    removed = 0
    for path in _stored_files(tree):
        if path.stem not in kept:
            path.unlink()
            removed += 1
    return removed


def _stored_files(tree: Path) -> list[Path]:
    objects = tree / audio_store.OBJECTS_DIRECTORY_NAME
    return sorted(objects.glob(f"*/*{WAV_SUFFIX}")) if objects.is_dir() else []
