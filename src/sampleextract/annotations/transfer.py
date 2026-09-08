from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from sqlalchemy import Connection

from samplecore.models.annotation import SampleAnnotation
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository

DEFAULT_ANNOTATION_FILE: Final[Path] = Path("annotations.jsonl")


@dataclass(frozen=True)
class TransferSummary:
    """How many annotations one export or import moved, and the file it moved them through."""

    annotations: int
    path: Path


def export_annotations(connection: Connection, *, path: Path) -> TransferSummary:
    """Write every hand annotation to a JSONL file, one annotation per line.

    Each line carries a whole annotation, anchor included, so the file stands on its own:
    `import_annotations` restores it into a database that has never held one. This is the copy that
    survives losing the database, which matters here more than anywhere else in the library, a
    person's own decisions being the one thing no pass can rebuild.
    """
    annotations = PostgresSampleAnnotationRepository(connection).list_all()
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for annotation in annotations:
            file.write(f"{annotation.model_dump_json()}\n")

    return TransferSummary(annotations=len(annotations), path=path)


def import_annotations(connection: Connection, *, path: Path) -> TransferSummary:
    """Read annotations back from a JSONL file, each replacing what the table holds for its sample.

    Reading adds and updates, so a file merges into whatever is already there and every sample it
    says nothing about keeps what it had.

    Raises:
        ValidationError: a line holds something other than an annotation.
    """
    annotations = tuple(
        SampleAnnotation.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() != ""
    )
    with start_batch(connection):
        PostgresSampleAnnotationRepository(connection).replace_many(annotations)

    return TransferSummary(annotations=len(annotations), path=path)
