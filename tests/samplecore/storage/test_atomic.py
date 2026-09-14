from __future__ import annotations

import stat
from pathlib import Path
from typing import IO

import pytest

from samplecore.storage.atomic import (
    PARTIAL_SUFFIX,
    PLAIN_FILE_MODE,
    synchronize_directory,
    synchronize_file,
    write_atomically,
    write_bytes_atomically,
)

PREVIOUS_CONTENT = b"what was there before"
NEW_CONTENT = b"the whole new content"


class WriterFailure(RuntimeError):
    pass


def _fail_halfway(stream: IO[bytes]) -> None:
    stream.write(NEW_CONTENT[:4])
    raise WriterFailure("stopped partway")


def test_a_written_file_holds_the_whole_content_with_plain_permissions(tmp_path: Path) -> None:
    destination = tmp_path / "nested" / "file.bin"

    write_atomically(destination, lambda stream: stream.write(NEW_CONTENT))

    assert destination.read_bytes() == NEW_CONTENT
    assert stat.S_IMODE(destination.stat().st_mode) == PLAIN_FILE_MODE


def test_a_writer_that_raises_leaves_the_previous_file_and_nothing_beside_it(tmp_path: Path) -> None:
    destination = tmp_path / "file.bin"
    destination.write_bytes(PREVIOUS_CONTENT)

    with pytest.raises(WriterFailure):
        write_atomically(destination, _fail_halfway)

    assert destination.read_bytes() == PREVIOUS_CONTENT
    assert not list(tmp_path.glob(f"*{PARTIAL_SUFFIX}"))


def test_a_new_file_replaces_the_previous_one(tmp_path: Path) -> None:
    destination = tmp_path / "file.bin"
    destination.write_bytes(PREVIOUS_CONTENT)

    write_atomically(destination, lambda stream: stream.write(NEW_CONTENT))

    assert destination.read_bytes() == NEW_CONTENT
    assert not list(tmp_path.glob(f"*{PARTIAL_SUFFIX}"))


def test_bytes_written_whole_replace_what_was_there(tmp_path: Path) -> None:
    destination = tmp_path / "file.bin"
    destination.write_bytes(PREVIOUS_CONTENT)

    write_bytes_atomically(destination, NEW_CONTENT)

    assert destination.read_bytes() == NEW_CONTENT
    assert [entry.name for entry in tmp_path.iterdir()] == ["file.bin"]


def test_flushing_a_file_and_its_directory_leaves_both_as_they_were(tmp_path: Path) -> None:
    written = tmp_path / "built-elsewhere.bin"
    written.write_bytes(NEW_CONTENT)

    synchronize_file(written)
    synchronize_directory(tmp_path)

    assert written.read_bytes() == NEW_CONTENT
