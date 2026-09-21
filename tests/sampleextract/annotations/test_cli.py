from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from samplecore.exit_status import ExitStatus
from samplecore.models.annotation import SampleAnnotation
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository
from sampleextract.annotations.cli import main

PROGRAM = "samplelibrary annotations"


def _write_config(tmp_path: Path, database_url: str) -> Path:
    module_source_directory = tmp_path / "modules"
    module_source_directory.mkdir()
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[library]\n"
        f'module_source_directory = "{module_source_directory.as_posix()}"\n'
        f'library_root = "{(tmp_path / "library").as_posix()}"\n'
        f'database_url = "{database_url}"\n',
        encoding="utf-8",
    )
    return config_path


@pytest.fixture
def configured(tmp_path: Path, _database_url: str, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    return tmp_path / "annotations.jsonl"


def test_export_reports_what_it_wrote(
    connection: Connection, stored_annotation: SampleAnnotation, configured: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["export", "--path", str(configured)], prog=PROGRAM)

    assert "Wrote 1 annotation(s)" in capsys.readouterr().out
    assert configured.exists()


def test_import_reads_a_file_back_into_the_catalog(
    connection: Connection, stored_annotation: SampleAnnotation, configured: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["export", "--path", str(configured)], prog=PROGRAM)
    repository = PostgresSampleAnnotationRepository(connection)
    repository.delete_many((stored_annotation.sample_hash,))
    connection.commit()

    main(["import", "--path", str(configured)], prog=PROGRAM)

    assert "Read 1 annotation(s)" in capsys.readouterr().out
    assert repository.get(stored_annotation.sample_hash) == stored_annotation


def test_relink_reports_a_label_it_reattached(
    connection: Connection,
    stored_annotation: SampleAnnotation,
    rehash_the_labeled_sample: Callable[[], str],
    configured: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rehash_the_labeled_sample()

    main(["relink"], prog=PROGRAM)

    assert "1 relinked" in capsys.readouterr().out


def test_relink_ends_a_success_naming_the_label_that_needs_a_person(
    connection: Connection,
    stored_annotation: SampleAnnotation,
    forget_the_labeled_occurrence: Callable[[], None],
    configured: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A label nobody can reattach automatically describes the library, so it is a warning and the pass succeeds."""
    forget_the_labeled_occurrence()

    main(["relink"], prog=PROGRAM)

    assert "Left alone" in capsys.readouterr().err


def test_a_command_is_required(configured: Path) -> None:
    with pytest.raises(SystemExit):
        main([], prog=PROGRAM)


def test_vocabulary_lists_the_tags_in_use_as_a_tree(
    connection: Connection, stored_annotation: SampleAnnotation, configured: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repository = PostgresSampleAnnotationRepository(connection)
    repository.upsert_many(
        (
            stored_annotation.model_copy(update={"label": "HI-HAT: CLOSED, LO-FI"}),
            stored_annotation.model_copy(update={"sample_hash": "d" * 64, "label": "HI-HAT: OPEN"}),
            stored_annotation.model_copy(update={"sample_hash": "e" * 64, "label": "ELECTRIC"}),
        )
    )
    connection.commit()

    main(["vocabulary"], prog=PROGRAM)

    reported = capsys.readouterr().out
    assert "    2  HI-HAT" in reported
    assert "        1  CLOSED" in reported
    assert "Carried by one sample each: ELECTRIC, HI-HAT: CLOSED, HI-HAT: OPEN, LO-FI." in reported


def test_an_import_from_a_file_that_is_not_there_ends_with_one_message(
    configured: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["import", "--path", str(tmp_path / "absent.jsonl")], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED
    reported = capsys.readouterr().err
    assert "Moved nothing:" in reported
    assert "Traceback" not in reported


def test_the_vocabulary_prints_its_lines_as_data(
    connection: Connection, stored_annotation: SampleAnnotation, configured: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    PostgresSampleAnnotationRepository(connection).upsert_many(
        (stored_annotation.model_copy(update={"label": "KICK"}),)
    )
    connection.commit()

    main(["vocabulary"], prog=PROGRAM)

    first_line = capsys.readouterr().out.splitlines()[0]
    assert re.match(r"^\s*1\s+KICK$", first_line)
