from __future__ import annotations

from pathlib import Path

from sqlalchemy import Connection

from samplecore.models.annotation import SampleAnnotation
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository
from sampleextract.annotations.transfer import export_annotations, import_annotations


def test_a_label_survives_a_round_trip_through_a_file(
    connection: Connection, stored_annotation: SampleAnnotation, tmp_path: Path
) -> None:
    path = tmp_path / "labels.jsonl"
    export_annotations(connection, path=path)
    repository = PostgresSampleAnnotationRepository(connection)
    repository.delete_many((stored_annotation.sample_hash,))
    connection.commit()

    import_annotations(connection, path=path)

    assert repository.get(stored_annotation.sample_hash) == stored_annotation


def test_an_export_writes_one_line_per_label(
    connection: Connection, stored_annotation: SampleAnnotation, tmp_path: Path
) -> None:
    path = tmp_path / "labels.jsonl"

    summary = export_annotations(connection, path=path)

    assert summary.annotations == 1
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_an_export_of_an_unlabeled_library_writes_an_empty_file(connection: Connection, tmp_path: Path) -> None:
    path = tmp_path / "labels.jsonl"

    summary = export_annotations(connection, path=path)

    assert summary.annotations == 0
    assert path.read_text(encoding="utf-8") == ""


def test_importing_keeps_every_label_the_file_says_nothing_about(
    connection: Connection, stored_annotation: SampleAnnotation, tmp_path: Path
) -> None:
    """A file merges into what is already on record, so importing never costs someone their work."""
    path = tmp_path / "labels.jsonl"
    other = stored_annotation.model_copy(update={"sample_hash": "d" * 64, "label": "kick"})
    repository = PostgresSampleAnnotationRepository(connection)
    repository.replace_many((other,))
    connection.commit()
    export_annotations(connection, path=path)
    repository.delete_many((other.sample_hash,))
    connection.commit()

    import_annotations(connection, path=path)

    assert repository.count() == 2


def test_importing_a_file_with_blank_lines_reads_only_the_labels(
    connection: Connection, stored_annotation: SampleAnnotation, tmp_path: Path
) -> None:
    path = tmp_path / "labels.jsonl"
    path.write_text(f"\n{stored_annotation.model_dump_json()}\n\n", encoding="utf-8")

    assert import_annotations(connection, path=path).annotations == 1
