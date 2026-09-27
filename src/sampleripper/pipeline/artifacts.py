from __future__ import annotations

import shutil
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import BaseModel

from samplecore.digests import digest_of_rows
from samplecore.hashing import file_sha256
from samplecore.models.base import FROZEN
from samplecore.models.sample_file import FileFingerprint
from samplecore.storage.atomic import write_bytes_atomically

SIDECAR_SUFFIX: Final[str] = ".pipeline.json"
CONTENT_KEY: Final[str] = "content"


class ArtifactSidecar(BaseModel):
    """What an artifact was built from, written beside it once it stands complete.

    The inputs are the named components the step read, the content digest is what the artifact holds
    now, and the fingerprint is what its file looked like then, so an artifact left as it was is
    verified by a status call and one written again is read in full.
    """

    model_config = FROZEN

    inputs: Mapping[str, str]
    digest: str
    content: str
    fingerprint: FileFingerprint
    completed_at: datetime


class StepRecord(BaseModel):
    """What a step's last complete run read and produced, kept for saying what has changed since.

    Nothing decides whether a step runs from this: it explains a decision the outputs themselves
    settle, and is safe to lose.
    """

    model_config = FROZEN

    inputs: Mapping[str, str]
    outputs: Mapping[str, str]
    completed_at: datetime


class ScratchIntent(BaseModel):
    """The record a run from scratch writes before it empties anything, and removes once it has.

    A run finding this in place finishes the emptying first, so a run stopped partway through it
    never leaves half a library behind.
    """

    model_config = FROZEN

    started_at: datetime


def sidecar_path(artifact: Path) -> Path:
    """Where the record of what an artifact was built from sits."""
    return artifact.with_name(f"{artifact.name}{SIDECAR_SUFFIX}")


def read_sidecar(artifact: Path) -> ArtifactSidecar | None:
    """What an artifact was built from, or nothing where no complete build recorded it."""
    path = sidecar_path(artifact)
    if not path.is_file():
        return None
    try:
        return ArtifactSidecar.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        return None


def seal_artifact(artifact: Path, *, inputs: Mapping[str, str], digest: str) -> ArtifactSidecar:
    """Bind an artifact to the inputs it was built from, reading what it holds now."""
    sidecar = ArtifactSidecar(
        inputs=inputs,
        digest=digest,
        content=content_digest(artifact),
        fingerprint=fingerprint_of(artifact),
        completed_at=datetime.now(UTC),
    )
    write_bytes_atomically(sidecar_path(artifact), sidecar.model_dump_json().encode("utf-8"))
    return sidecar


def artifact_holds_its_content(artifact: Path, sidecar: ArtifactSidecar) -> bool:
    """Whether an artifact is the one its record describes, re-reading it only where its file moved."""
    if not artifact.exists():
        return False
    if fingerprint_of(artifact) == sidecar.fingerprint:
        return True
    return content_digest(artifact) == sidecar.content


def content_digest(artifact: Path) -> str:
    """What an artifact holds: a file's own digest, or one over every file of a directory.

    A directory digests by each file's path and size beside the digest of everything small enough to
    read whole, which is what tells one build of a cache from another without reading gigabytes.
    """
    if artifact.is_dir():
        return digest_of_rows(
            (path.relative_to(artifact).as_posix(), path.stat().st_size, _digest_of_small_file(path))
            for path in sorted(path for path in artifact.rglob("*") if path.is_file())
        )
    return file_sha256(artifact)


def fingerprint_of(artifact: Path) -> FileFingerprint:
    """What an artifact's file looked like when it was read, a directory standing for its own entry."""
    return FileFingerprint.of(artifact.stat())


def read_step_record(path: Path) -> StepRecord | None:
    """What a step's last complete run read and produced, or nothing where none is recorded."""
    if not path.is_file():
        return None
    try:
        return StepRecord.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        return None


def write_step_record(path: Path, *, inputs: Mapping[str, str], outputs: Mapping[str, str]) -> None:
    """Record what a step read and produced, for a later run to say what has changed since."""
    record = StepRecord(inputs=inputs, outputs=outputs, completed_at=datetime.now(UTC))
    write_bytes_atomically(path, record.model_dump_json().encode("utf-8"))


SMALL_FILE_BYTES: Final[int] = 16 * 1024 * 1024


def _digest_of_small_file(path: Path) -> str | None:
    """The digest of a file small enough to read whole, and nothing for one larger."""
    return file_sha256(path) if path.stat().st_size <= SMALL_FILE_BYTES else None


def remove_path(path: Path) -> tuple[Path, ...]:
    """Delete a file or a whole directory where one is there, naming what went and nothing where none was."""
    if path.is_dir():
        shutil.rmtree(path)
        return (path,)
    if path.exists():
        path.unlink()
        return (path,)
    return ()
