from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from sqlalchemy import Connection

from samplecore.models.label import SampleLabel
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.sample_label import PostgresSampleLabelRepository

DEFAULT_LABEL_FILE: Final[Path] = Path("labels.jsonl")


@dataclass(frozen=True)
class TransferSummary:
    """How many labels one export or import moved, and the file it moved them through."""

    labels: int
    path: Path


def export_labels(connection: Connection, *, path: Path) -> TransferSummary:
    """Write every hand label to a JSONL file, one label per line.

    Each line carries a whole label, anchor included, so the file stands on its own: `import_labels`
    restores it into a database that has never held a label. This is the copy that survives losing
    the database, which matters here more than anywhere else in the library, hand labels being the
    one thing no pass can rebuild.
    """
    labels = PostgresSampleLabelRepository(connection).list_all()
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for label in labels:
            file.write(f"{label.model_dump_json()}\n")

    return TransferSummary(labels=len(labels), path=path)


def import_labels(connection: Connection, *, path: Path) -> TransferSummary:
    """Read labels back from a JSONL file, each replacing what the table holds for its own sample.

    Reading adds and updates, so a file merges into whatever is already there and every label it
    says nothing about is kept.

    Raises:
        ValidationError: a line holds something other than a label.
    """
    labels = tuple(
        SampleLabel.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() != ""
    )
    with start_batch(connection):
        PostgresSampleLabelRepository(connection).upsert_many(labels)

    return TransferSummary(labels=len(labels), path=path)
