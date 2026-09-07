from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from samplecore.models.label import SampleLabel
from samplecore.storage.repositories.sample_label import PostgresSampleLabelRepository
from sampleextract.labels.cli import main


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
    return tmp_path / "labels.jsonl"


def test_export_reports_what_it_wrote(
    connection: Connection, stored_label: SampleLabel, configured: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["export", "--path", str(configured)])

    assert "Wrote 1 label(s)" in capsys.readouterr().out
    assert configured.exists()


def test_import_reads_a_file_back_into_the_catalog(
    connection: Connection, stored_label: SampleLabel, configured: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["export", "--path", str(configured)])
    repository = PostgresSampleLabelRepository(connection)
    repository.delete_many((stored_label.sample_hash,))
    connection.commit()

    main(["import", "--path", str(configured)])

    assert "Read 1 label(s)" in capsys.readouterr().out
    assert repository.get(stored_label.sample_hash) == stored_label


def test_relink_reports_a_label_it_reattached(
    connection: Connection,
    stored_label: SampleLabel,
    rehash_the_labelled_sample: Callable[[], str],
    configured: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rehash_the_labelled_sample()

    main(["relink"])

    assert "1 relinked" in capsys.readouterr().out


def test_relink_exits_nonzero_when_a_label_needs_a_person(
    connection: Connection,
    stored_label: SampleLabel,
    forget_the_labelled_occurrence: Callable[[], None],
    configured: Path,
) -> None:
    """A label nobody can reattach automatically is worth failing the command over."""
    forget_the_labelled_occurrence()

    with pytest.raises(SystemExit) as exit_info:
        main(["relink"])

    assert exit_info.value.code == 1


def test_a_command_is_required(configured: Path) -> None:
    with pytest.raises(SystemExit):
        main([])
