from __future__ import annotations

import os
from pathlib import Path

from samplelibrary.pipeline.artifacts import (
    artifact_holds_its_content,
    content_digest,
    read_sidecar,
    read_step_record,
    remove_path,
    seal_artifact,
    sidecar_path,
    write_step_record,
)

INPUTS = {"samples": "a" * 64, "parameters": "b" * 64}


def _artifact(tmp_path: Path, content: bytes = b"a model") -> Path:
    artifact = tmp_path / "descriptor-0123456789abcdef.pt"
    artifact.write_bytes(content)
    return artifact


def test_a_sealed_artifact_carries_what_it_was_built_from(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)

    sealed = seal_artifact(artifact, inputs=INPUTS, digest="0123456789abcdef")

    read_back = read_sidecar(artifact)
    assert read_back == sealed
    assert read_back is not None and read_back.inputs == INPUTS
    assert sidecar_path(artifact).name.endswith(".pipeline.json")
    assert artifact_holds_its_content(artifact, read_back)


def test_an_artifact_written_again_no_longer_holds_what_its_record_describes(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    sealed = seal_artifact(artifact, inputs=INPUTS, digest="0123456789abcdef")

    artifact.write_bytes(b"another model")

    assert not artifact_holds_its_content(artifact, sealed)


def test_an_artifact_left_exactly_as_it_was_reads_as_the_one_recorded(tmp_path: Path) -> None:
    """A stat call settles it where the file is untouched, so verifying costs nothing on a large artifact."""
    artifact = _artifact(tmp_path)
    sealed = seal_artifact(artifact, inputs=INPUTS, digest="0123456789abcdef")
    status = artifact.stat()

    os.utime(artifact, ns=(status.st_atime_ns, status.st_mtime_ns + 1_000_000_000))

    assert artifact_holds_its_content(artifact, sealed)
    assert content_digest(artifact) == sealed.content


def test_a_directory_artifact_digests_by_everything_it_holds(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    (cache / "inner").mkdir(parents=True)
    (cache / "description.json").write_text("{}", encoding="utf-8")
    (cache / "inner" / "grids.npy").write_bytes(b"0" * 32)
    before = content_digest(cache)

    (cache / "inner" / "grids.npy").write_bytes(b"1" * 32)

    assert content_digest(cache) != before


def test_a_gone_artifact_holds_nothing(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    sealed = seal_artifact(artifact, inputs=INPUTS, digest="0123456789abcdef")

    assert remove_path(artifact) == (artifact,)
    assert remove_path(artifact) == ()
    assert not artifact_holds_its_content(artifact, sealed)


def test_a_step_record_says_what_a_step_read_and_produced(tmp_path: Path) -> None:
    path = tmp_path / "steps" / "descriptor.json"

    write_step_record(path, inputs=INPUTS, outputs={"content": "c" * 64})

    record = read_step_record(path)
    assert record is not None
    assert (record.inputs, record.outputs) == (INPUTS, {"content": "c" * 64})
    assert read_step_record(tmp_path / "steps" / "absent.json") is None


def test_a_record_a_stopped_run_left_half_written_reads_as_none(tmp_path: Path) -> None:
    path = tmp_path / "steps" / "descriptor.json"
    write_step_record(path, inputs=INPUTS, outputs={})
    path.write_text(path.read_text(encoding="utf-8")[: len(path.read_text(encoding="utf-8")) // 2], encoding="utf-8")

    assert read_step_record(path) is None
