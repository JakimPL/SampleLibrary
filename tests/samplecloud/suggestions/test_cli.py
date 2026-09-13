from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecloud.suggestions import cli
from samplecloud.suggestions.cli import main
from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.label_suggestion import PostgresSampleLabelSuggestionRepository
from tests.samplecloud.backends.test_teacher_backend import RecordingTeacher
from tests.samplecloud.suggestions.test_scoring import KICK_HASH, VOCABULARY, seed_listening_experiment

PROGRAM = "samplelibrary cloud suggest"


def _write_config(tmp_path: Path, database_url: str) -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[library]\nmodule_source_directory = "{tmp_path.as_posix()}"\nlibrary_root = "{tmp_path.as_posix()}"\n'
        f'database_url = "{database_url}"\n',
        encoding="utf-8",
    )
    return config_path


def test_the_command_scores_a_listening_experiment_and_reports_the_agreement(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    monkeypatch.setattr(cli, "load_teacher", lambda *, device: RecordingTeacher())
    listing = tmp_path / "labels.txt"
    listing.write_text("\n".join(VOCABULARY), encoding="utf-8")
    source = seed_listening_experiment(connection)

    main(["--experiment-id", str(source), "--vocabulary", str(listing), "--top", "1"], prog=PROGRAM)

    repository = PostgresSampleLabelSuggestionRepository(connection)
    latest = repository.latest_experiment_id()
    assert latest is not None
    assert [suggestion.label for suggestion in repository.get_many(latest, [KICK_HASH])[KICK_HASH]] == ["BASS DRUM"]
    output = capsys.readouterr().out
    assert "suggested labels for 2 samples" in output
    assert "Against 2 hand labels" in output


def test_an_experiment_of_another_backend_is_refused(
    connection: Connection, _database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    other = PostgresExperimentRepository(connection).create(backend_name="librosa", label=None, params={})
    connection.commit()

    with pytest.raises(ValueError, match="librosa backend"):
        main(["--experiment-id", str(other)], prog=PROGRAM)
