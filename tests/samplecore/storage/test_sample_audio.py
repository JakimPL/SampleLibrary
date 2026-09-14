from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
import soundfile
from sqlalchemy import Connection

from samplecore.models.sample_file import FileFingerprint, SampleFile, SampleFileLocation
from samplecore.sample_files.decoding import decode_sample_file
from samplecore.storage import audio_store
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_file import PostgresSampleFileRepository
from samplecore.storage.sample_audio import SampleAudio, SampleUnavailableError, is_unchanged

RATE = 44100
FRAMES = 256


@pytest.fixture
def sample_directory(tmp_path: Path) -> Path:
    directory = tmp_path / "packs"
    (directory / "drums").mkdir(parents=True)
    return directory


@pytest.fixture
def library_root(tmp_path: Path) -> Path:
    return tmp_path / "library"


@pytest.fixture
def kick_path(sample_directory: Path) -> Path:
    path = sample_directory / "drums" / "kick.wav"
    soundfile.write(path, np.linspace(-0.8, 0.8, FRAMES), RATE, subtype="PCM_16")
    return path


@pytest.fixture
def kick_copy_path(sample_directory: Path, kick_path: Path) -> Path:
    path = sample_directory / "kick copy.wav"
    path.write_bytes(kick_path.read_bytes())
    return path


def _cataloged(sample_directory: Path, path: Path) -> SampleFile:
    decoded = decode_sample_file(path)
    return SampleFile(
        sample_hash=decoded.sample_pcm.sample.hash,
        location=SampleFileLocation(
            directory=sample_directory, relative_path=path.relative_to(sample_directory).as_posix()
        ),
        rate=decoded.rate,
        fingerprint=FileFingerprint.of(path.stat()),
    )


def test_a_sample_found_in_a_file_is_read_from_that_file(
    library_root: Path, sample_directory: Path, kick_path: Path
) -> None:
    kick = _cataloged(sample_directory, kick_path)
    audio = SampleAudio.of_files(library_root, (kick,))
    decoded = decode_sample_file(kick_path)

    read = audio.read(decoded.sample_pcm.sample)

    assert read.sample == decoded.sample_pcm.sample
    assert np.array_equal(read.pcm, decoded.sample_pcm.pcm)
    assert np.array_equal(audio.read_by_hash(kick.sample_hash).pcm, decoded.sample_pcm.pcm)
    assert audio.frame_count(kick.sample_hash) == FRAMES


def test_a_stored_object_is_read_from_the_store(library_root: Path, sample_directory: Path, kick_path: Path) -> None:
    decoded = decode_sample_file(kick_path)
    audio_store.write(library_root, decoded.sample_pcm)
    kick_path.unlink()
    audio = SampleAudio.of_files(library_root, ())

    assert np.array_equal(audio.read(decoded.sample_pcm.sample).pcm, decoded.sample_pcm.pcm)
    assert audio.is_available(decoded.sample_pcm.sample.hash)


def test_a_sample_whose_file_is_gone_is_unavailable(
    library_root: Path, sample_directory: Path, kick_path: Path
) -> None:
    kick = _cataloged(sample_directory, kick_path)
    audio = SampleAudio.of_files(library_root, (kick,))
    sample = decode_sample_file(kick_path).sample_pcm.sample
    kick_path.unlink()

    assert not audio.is_available(kick.sample_hash)
    with pytest.raises(SampleUnavailableError, match="kick.wav"):
        audio.read(sample)
    with pytest.raises(SampleUnavailableError):
        audio.frame_count(kick.sample_hash)


def test_a_file_written_again_since_its_scan_is_unavailable(
    library_root: Path, sample_directory: Path, kick_path: Path
) -> None:
    kick = _cataloged(sample_directory, kick_path)
    soundfile.write(kick_path, np.linspace(0.8, -0.8, FRAMES * 2), RATE, subtype="PCM_16")

    assert not is_unchanged(kick)
    with pytest.raises(SampleUnavailableError):
        SampleAudio.of_files(library_root, (kick,)).read_by_hash(kick.sample_hash)


def test_a_file_holding_other_frames_behind_its_old_fingerprint_is_unavailable(
    library_root: Path, sample_directory: Path, kick_path: Path
) -> None:
    kick = _cataloged(sample_directory, kick_path)
    soundfile.write(kick_path, np.linspace(0.8, -0.8, FRAMES), RATE, subtype="PCM_16")
    os.utime(kick_path, ns=(kick.fingerprint.modified_ns, kick.fingerprint.modified_ns))

    assert is_unchanged(kick)
    with pytest.raises(SampleUnavailableError):
        SampleAudio.of_files(library_root, (kick,)).read_by_hash(kick.sample_hash)


def test_a_sample_is_read_from_another_of_its_files_when_the_first_is_gone(
    library_root: Path, sample_directory: Path, kick_path: Path, kick_copy_path: Path
) -> None:
    copy = _cataloged(sample_directory, kick_copy_path)
    kick = _cataloged(sample_directory, kick_path)
    audio = SampleAudio.of_files(library_root, (kick, copy))
    kick_copy_path.unlink()

    assert audio.files_by_hash[kick.sample_hash] == (kick, copy)
    assert audio.read_by_hash(kick.sample_hash).sample.hash == kick.sample_hash


def test_a_sample_neither_stored_nor_found_in_a_file_is_a_damaged_store(library_root: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no object is stored"):
        SampleAudio.of_files(library_root, ()).read_by_hash("e" * 64)


def test_the_catalog_supplies_every_sample_file(
    connection: Connection, library_root: Path, sample_directory: Path, kick_path: Path
) -> None:
    kick = _cataloged(sample_directory, kick_path)
    PostgresSampleRepository(connection).upsert(decode_sample_file(kick_path).sample_pcm.sample)
    PostgresSampleFileRepository(connection).upsert(kick)
    connection.commit()

    assert SampleAudio.from_catalog(connection, library_root).files_by_hash == {kick.sample_hash: (kick,)}
