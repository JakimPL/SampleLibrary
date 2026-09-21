from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecore.models.annotation import SampleAnnotation, SampleFileAnchor
from samplecore.models.sample_file import SampleFileLocation
from samplecore.storage.repositories.annotation_import import PostgresAnnotationImportRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository
from sampleextract.annotations.transfer import AnnotationFileRefused, export_annotations, import_annotations


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


def test_a_label_anchored_to_a_sample_file_survives_a_round_trip_through_a_file(
    connection: Connection, stored_annotation: SampleAnnotation, tmp_path: Path
) -> None:
    path = tmp_path / "labels.jsonl"
    anchored_to_a_file = stored_annotation.model_copy(
        update={
            "anchor": SampleFileAnchor(
                location=SampleFileLocation(directory=Path("/samples"), relative_path="Kicks/Deep 01.wav")
            )
        }
    )
    repository = PostgresSampleAnnotationRepository(connection)
    repository.upsert_many((anchored_to_a_file,))
    connection.commit()
    export_annotations(connection, path=path)
    repository.delete_many((anchored_to_a_file.sample_hash,))
    connection.commit()

    import_annotations(connection, path=path)

    assert repository.get(anchored_to_a_file.sample_hash) == anchored_to_a_file


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
    repository.upsert_many((other,))
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


NEXT_LINE = chr(0x85)
LINE_SEPARATOR = chr(0x2028)


def test_a_sample_name_holding_a_line_separator_survives_a_round_trip(
    connection: Connection, stored_annotation: SampleAnnotation, tmp_path: Path
) -> None:
    """Module text is read as Latin-1, so a sample name can carry U+0085 and its Unicode relatives."""
    path = tmp_path / "labels.jsonl"
    odd = stored_annotation.model_copy(update={"sample_name": f"voice{NEXT_LINE}one{LINE_SEPARATOR}two"})
    repository = PostgresSampleAnnotationRepository(connection)
    repository.upsert_many((odd,))
    connection.commit()
    export_annotations(connection, path=path)
    repository.delete_many((odd.sample_hash,))
    connection.commit()

    import_annotations(connection, path=path)

    assert repository.get(odd.sample_hash) == odd


def test_a_file_speaking_for_one_sample_twice_is_refused_whole(
    connection: Connection, stored_annotation: SampleAnnotation, tmp_path: Path
) -> None:
    path = tmp_path / "labels.jsonl"
    changed = stored_annotation.model_copy(update={"label": "KICK"})
    path.write_text(f"{stored_annotation.model_dump_json()}\n{changed.model_dump_json()}\n", encoding="utf-8")

    with pytest.raises(AnnotationFileRefused, match="lines 1, 2"):
        import_annotations(connection, path=path)

    assert PostgresSampleAnnotationRepository(connection).get(stored_annotation.sample_hash) == stored_annotation


@pytest.mark.parametrize(
    ("content", "reason"),
    [(None, "cannot be read"), ("{}\n", "line 1 of"), ("not json\n", "line 1 of")],
    ids=("a missing file", "a line missing the annotation's fields", "a line that is no JSON"),
)
def test_a_file_that_is_no_list_of_annotations_is_refused(
    connection: Connection, tmp_path: Path, content: str | None, reason: str
) -> None:
    path = tmp_path / "labels.jsonl"
    if content is not None:
        path.write_text(content, encoding="utf-8")

    with pytest.raises(AnnotationFileRefused, match=reason):
        import_annotations(connection, path=path)


def test_exporting_beneath_a_file_is_refused(connection: Connection, tmp_path: Path) -> None:
    blocking_file = tmp_path / "labels"
    blocking_file.write_text("", encoding="utf-8")

    with pytest.raises(AnnotationFileRefused, match="cannot be written"):
        export_annotations(connection, path=blocking_file / "labels.jsonl")


def test_exporting_into_a_directory_that_is_not_there_creates_it(connection: Connection, tmp_path: Path) -> None:
    path = tmp_path / "absent" / "labels.jsonl"

    summary = export_annotations(connection, path=path)

    assert summary.annotations == 0
    assert path.read_text(encoding="utf-8") == ""


def test_an_export_replacing_an_earlier_one_leaves_no_partial_file_beside_it(
    connection: Connection, tmp_path: Path
) -> None:
    path = tmp_path / "labels.jsonl"
    path.write_text("an earlier export\n", encoding="utf-8")

    export_annotations(connection, path=path)

    assert path.read_text(encoding="utf-8") == ""
    assert [entry.name for entry in tmp_path.iterdir()] == ["labels.jsonl"]


def test_an_import_records_the_file_it_read_by_the_digest_of_its_bytes(
    connection: Connection, stored_annotation: SampleAnnotation, tmp_path: Path
) -> None:
    path = tmp_path / "labels.jsonl"
    export_annotations(connection, path=path)
    moved = tmp_path / "elsewhere" / "the same labels.jsonl"
    moved.parent.mkdir()
    moved.write_bytes(path.read_bytes())
    imports = PostgresAnnotationImportRepository(connection)

    import_annotations(connection, path=path)
    first = imports.get(hashlib.sha256(path.read_bytes()).hexdigest())
    import_annotations(connection, path=moved)
    again = imports.get(hashlib.sha256(path.read_bytes()).hexdigest())

    assert first is not None and again is not None
    assert first.annotation_count == again.annotation_count == 1
    assert again.imported_at >= first.imported_at


def test_a_refused_import_records_nothing(connection: Connection, tmp_path: Path) -> None:
    path = tmp_path / "labels.jsonl"
    path.write_bytes(b"\xff\xfe not text\n")

    with pytest.raises(AnnotationFileRefused, match="cannot be read"):
        import_annotations(connection, path=path)

    assert PostgresAnnotationImportRepository(connection).get(hashlib.sha256(path.read_bytes()).hexdigest()) is None


def test_a_carriage_return_inside_a_line_keeps_the_line_whole(
    connection: Connection, stored_annotation: SampleAnnotation, tmp_path: Path
) -> None:
    """A module's text can hold a bare carriage return, and the file splits on the newlines the export writes alone."""
    named = stored_annotation.model_copy(
        update={"anchor": stored_annotation.anchor.model_copy(update={"sample_name": "kick\rsnare"})}
    )
    repository = PostgresSampleAnnotationRepository(connection)
    repository.upsert_many((named,))
    connection.commit()
    path = tmp_path / "labels.jsonl"
    export_annotations(connection, path=path)
    repository.delete_many((named.sample_hash,))
    connection.commit()

    summary = import_annotations(connection, path=path)

    assert summary.annotations == 1
    assert repository.get(named.sample_hash) == named
