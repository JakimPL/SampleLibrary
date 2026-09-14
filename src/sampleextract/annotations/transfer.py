from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError
from sqlalchemy import Connection

from samplecore.models.annotation import SampleAnnotation
from samplecore.storage.atomic import write_bytes_atomically
from samplecore.storage.curation import claim_annotation_writes, register_tag_ranks
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository

DEFAULT_ANNOTATION_FILE: Final[Path] = Path("annotations.jsonl")


class AnnotationFileRefused(ValueError):
    """Raised when an annotations file cannot be read or written as the list of annotations it stands for."""


@dataclass(frozen=True)
class TransferSummary:
    """How many annotations one export or import moved, and the file it moved them through."""

    annotations: int
    path: Path


def export_annotations(connection: Connection, *, path: Path) -> TransferSummary:
    """Write every hand annotation to a JSONL file, one annotation per line.

    The file lands whole or leaves an earlier export at that path as it was. Each line carries a
    whole annotation, anchor included, so the file stands on its own:
    `import_annotations` restores it into a database that has never held one. This is the copy that
    survives losing the database, which matters here more than anywhere else in the library, a
    person's own decisions being the one thing no pass can rebuild.

    Raises:
        AnnotationFileRefused: the file cannot be written.
    """
    annotations = PostgresSampleAnnotationRepository(connection).list_all()
    lines = "".join(f"{annotation.model_dump_json()}\n" for annotation in annotations).encode("utf-8")
    try:
        write_bytes_atomically(path, lines)
    except OSError as error:
        raise AnnotationFileRefused(f"{path} cannot be written ({error.strerror})") from error

    return TransferSummary(annotations=len(annotations), path=path)


def import_annotations(connection: Connection, *, path: Path) -> TransferSummary:
    """Read annotations back from a JSONL file, each replacing what the table holds for its sample.

    Reading adds and updates, so a file merges into whatever is already there and every sample it
    says nothing about keeps what it had; a sample the file does speak for holds the file's decisions
    afterward, whatever it held before. The whole file lands in one transaction, or none of it does.

    Raises:
        AnnotationFileRefused: the file cannot be read, a line holds something other than an
            annotation, or the file speaks for one sample on more than one line.
    """
    annotations = _read_annotation_lines(path)
    with start_batch(connection):
        claim_annotation_writes(connection)
        PostgresSampleAnnotationRepository(connection).upsert_many(annotations)
        register_tag_ranks(
            connection,
            (item.label for item in sorted(annotations, key=lambda item: item.annotated_at) if item.label is not None),
        )

    return TransferSummary(annotations=len(annotations), path=path)


def _read_annotation_lines(path: Path) -> tuple[SampleAnnotation, ...]:
    """Every annotation in a JSONL file, one per line ending in a newline.

    A sample name may carry any character a module's text held, the Unicode line separators among
    them, so the file is split on the newlines the export writes and on nothing else.

    Raises:
        AnnotationFileRefused: the file cannot be read, a line holds something other than an
            annotation, or the file speaks for one sample on more than one line.
    """
    line_numbers_by_hash: dict[str, list[int]] = defaultdict(list)
    annotations: list[SampleAnnotation] = []
    try:
        with path.open(encoding="utf-8", newline="") as file:
            for line_number, line in enumerate(file, start=1):
                if line.strip() == "":
                    continue
                annotation = _annotation_on(line, line_number=line_number, path=path)
                line_numbers_by_hash[annotation.sample_hash].append(line_number)
                annotations.append(annotation)
    except (OSError, UnicodeDecodeError) as error:
        raise AnnotationFileRefused(f"{path} cannot be read ({error})") from error

    repeated = {sample_hash: lines for sample_hash, lines in line_numbers_by_hash.items() if len(lines) > 1}
    if repeated:
        described = "; ".join(
            f"{sample_hash} on lines {', '.join(str(number) for number in lines)}"
            for sample_hash, lines in sorted(repeated.items())
        )
        raise AnnotationFileRefused(f"{path} speaks for a sample on more than one line: {described}")
    return tuple(annotations)


def _annotation_on(line: str, *, line_number: int, path: Path) -> SampleAnnotation:
    """The annotation one line of the file holds.

    Raises:
        AnnotationFileRefused: the line holds something other than an annotation.
    """
    try:
        return SampleAnnotation.model_validate_json(line)
    except ValidationError as error:
        first = error.errors()[0]
        location = ".".join(str(part) for part in first["loc"]) or "the line"
        raise AnnotationFileRefused(
            f"line {line_number} of {path} holds no annotation: {location}: {first['msg']}"
        ) from error
