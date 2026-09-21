from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Connection

from samplecore.digests import digest_of_rows
from samplecore.models.sample import Sample
from samplecore.models.sample_file import FileFingerprint, SampleFile, SampleFileLocation
from samplecore.models.sample_pcm import SamplePCM
from samplecore.sample_files.decoding import UNREADABLE_SAMPLE_FILE_ERRORS, decode_sample_file, sample_file_frame_count
from samplecore.storage import audio_store
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_file import PostgresSampleFileRepository


class SampleUnavailableError(Exception):
    """Raised when a sample's audio lives only in sample files, and none of them holds it any more."""


@dataclass(frozen=True)
class SampleAudio:
    """Where every sample's audio is read from: the content store, or the files it is cataloged in.

    A sample extracted from a module has an object in the store; a sample found in a sample directory
    is read from its file, in place. A file can be gone, unreadable, or rewritten since it was hashed,
    so each of a sample's files is tried in location order and taken only while its fingerprint still
    matches and it still decodes to the sample's hash. A pass meets a sample none of whose files
    qualifies as ``SampleUnavailableError`` and carries on without it; a missing stored object is a
    damaged store and surfaces as ``FileNotFoundError``.
    """

    library_root: Path
    files_by_hash: Mapping[str, tuple[SampleFile, ...]]

    @classmethod
    def from_catalog(cls, connection: Connection, library_root: Path) -> SampleAudio:
        """The audio of every sample the catalog holds, reading its sample files from the catalog."""
        return cls.of_files(library_root, PostgresSampleFileRepository(connection).list_all())

    @classmethod
    def of_files(cls, library_root: Path, sample_files: Iterable[SampleFile]) -> SampleAudio:
        """The audio of the store under ``library_root`` together with the given sample files."""
        files_by_hash: dict[str, list[SampleFile]] = {}
        for sample_file in sorted(sample_files, key=lambda found: found.location.sort_key):
            files_by_hash.setdefault(sample_file.sample_hash, []).append(sample_file)
        return cls(
            library_root=library_root,
            files_by_hash={sample_hash: tuple(found) for sample_hash, found in files_by_hash.items()},
        )

    def read(self, sample: Sample) -> SamplePCM:
        """A cataloged sample's waveform, from its stored object or else from one of its files.

        Raises:
            SampleUnavailableError: the sample lives only in files, and none of them holds it now.
            FileNotFoundError: the sample has neither a stored object nor a cataloged file.
        """
        if audio_store.object_path(self.library_root, sample.hash).is_file():
            return audio_store.read(self.library_root, sample)
        return self._read_from_files(sample.hash)

    def read_by_hash(self, sample_hash: str) -> SamplePCM:
        """A sample's waveform by its hash alone, for a process holding no catalog.

        Raises:
            SampleUnavailableError: the sample lives only in files, and none of them holds it now.
            FileNotFoundError: the sample has neither a stored object nor a file given here.
        """
        if audio_store.object_path(self.library_root, sample_hash).is_file():
            return audio_store.read_object(self.library_root, sample_hash)
        return self._read_from_files(sample_hash)

    def frame_count(self, sample_hash: str) -> int:
        """How many frames a sample holds, read from a header alone.

        Raises:
            SampleUnavailableError: the sample lives only in files, and none of them holds it now.
            FileNotFoundError: the sample has neither a stored object nor a file given here.
        """
        if audio_store.object_path(self.library_root, sample_hash).is_file():
            return audio_store.stored_frame_count(self.library_root, sample_hash)
        for sample_file in self._files_of(sample_hash):
            if not is_unchanged(sample_file):
                continue
            try:
                return sample_file_frame_count(sample_file.location.path)
            except UNREADABLE_SAMPLE_FILE_ERRORS:
                continue
        raise _unavailable(sample_hash, self._files_of(sample_hash))

    def location_to_read(self, sample_hash: str) -> SampleFileLocation | None:
        """Where a process holding no catalog reads a sample from: the first of its files still as scanned.

        ``None`` for a sample the store holds an object of, which such a process reads by its hash,
        and for a sample no file is given here for.

        Raises:
            SampleUnavailableError: the sample lives only in sample files, and every one of them is gone or changed.
        """
        sample_files = self.files_by_hash.get(sample_hash, ())
        if audio_store.object_path(self.library_root, sample_hash).is_file() or not sample_files:
            return None
        for sample_file in sample_files:
            if is_unchanged(sample_file):
                return sample_file.location
        raise _unavailable(sample_hash, sample_files)

    def is_available(self, sample_hash: str) -> bool:
        """Whether the sample has a stored object, or a file whose fingerprint still matches."""
        return audio_store.object_path(self.library_root, sample_hash).is_file() or any(
            is_unchanged(sample_file) for sample_file in self.files_by_hash.get(sample_hash, ())
        )

    def _read_from_files(self, sample_hash: str) -> SamplePCM:
        for sample_file in self._files_of(sample_hash):
            sample_pcm = _decoded_if_unchanged(sample_file)
            if sample_pcm is not None:
                return sample_pcm
        raise _unavailable(sample_hash, self._files_of(sample_hash))

    def _files_of(self, sample_hash: str) -> tuple[SampleFile, ...]:
        """The files a sample is cataloged in.

        Raises:
            FileNotFoundError: the sample has no stored object and no cataloged file.
        """
        sample_files = self.files_by_hash.get(sample_hash, ())
        if not sample_files:
            raise FileNotFoundError(f"no object is stored for sample {sample_hash}")
        return sample_files


def readable_sample_hashes(connection: Connection) -> frozenset[str]:
    """Every cataloged sample whose audio can be read now as far as a status call tells.

    A sample a module holds is read from the store; one found only in sample directories is read
    from a file still standing with the size and write time it was scanned at. A file that stands
    unchanged decodes the way it did when it was scanned, the formats read being lossless, so this
    is the set a pass reading every sample reaches, told without decoding anything.
    """
    readable = set(PostgresSampleRepository(connection).hashes_held_by_modules())
    readable.update(
        sample_file.sample_hash
        for sample_file in PostgresSampleFileRepository(connection).list_all()
        if is_unchanged(sample_file)
    )
    return frozenset(readable)


def readable_membership_digest(connection: Connection) -> str:
    """One digest over the samples whose audio can be read now, so a pass can tell whether that set moved."""
    return digest_of_rows((sample_hash,) for sample_hash in sorted(readable_sample_hashes(connection)))


def is_unchanged(sample_file: SampleFile) -> bool:
    """Whether a cataloged file is still there with the size and write time it was hashed at."""
    try:
        status = sample_file.location.path.stat()
    except OSError:
        return False
    return FileFingerprint.of(status) == sample_file.fingerprint


def read_sample_file(location: SampleFileLocation, sample_hash: str) -> SamplePCM:
    """A sample's waveform read from a file said to hold it, for a process holding no catalog.

    The file is taken only when it decodes to the hash asked for, which is what lets a location
    handed over by a catalog reader stand in for a fingerprint.

    Raises:
        SampleUnavailableError: the file is gone, unreadable, or holds another sample now.
    """
    sample_pcm = _decoded_as(location, sample_hash)
    if sample_pcm is None:
        raise SampleUnavailableError(f"{location.path} is gone, unreadable, or holds another sample than {sample_hash}")
    return sample_pcm


def read_sample_file_frame_count(location: SampleFileLocation) -> int:
    """How many frames a sample file holds, from its header alone, for a process holding no catalog.

    Raises:
        SampleUnavailableError: the file is gone or unreadable.
    """
    try:
        return sample_file_frame_count(location.path)
    except UNREADABLE_SAMPLE_FILE_ERRORS as error:
        raise SampleUnavailableError(f"{location.path} is gone or unreadable: {error}") from error


def _decoded_if_unchanged(sample_file: SampleFile) -> SamplePCM | None:
    return _decoded_as(sample_file.location, sample_file.sample_hash) if is_unchanged(sample_file) else None


def _decoded_as(location: SampleFileLocation, sample_hash: str) -> SamplePCM | None:
    try:
        decoded = decode_sample_file(location.path)
    except UNREADABLE_SAMPLE_FILE_ERRORS:
        return None
    return decoded.sample_pcm if decoded.sample_pcm.sample.hash == sample_hash else None


def _unavailable(sample_hash: str, sample_files: tuple[SampleFile, ...]) -> SampleUnavailableError:
    return SampleUnavailableError(
        f"sample {sample_hash} is unavailable: {sample_files[0].location.path} and any other file it was "
        "found in are gone, unreadable or changed since they were scanned"
    )
