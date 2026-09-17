from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecloud.backends.teacher_backend import TEACHER_BACKEND_NAME
from samplecloud.categories import cli
from samplecloud.categories.cli import main
from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from samplecore.exit_status import ExitStatus
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.label_suggestion import PostgresSampleLabelSuggestionRepository
from tests.samplecloud.backends.test_teacher_backend import RecordingTeacher
from tests.samplecloud.categories.test_scoring import KICK_HASH, VOCABULARY, seed_listening_experiment

PROGRAM = "samplelibrary cloud categorize"


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
    shown = repository.shown_experiment_id()
    assert shown is not None
    assert [category.label for category in repository.get_many(shown, [KICK_HASH])[KICK_HASH]] == ["BASS DRUM"]
    output = capsys.readouterr().out
    assert "categorized 2 samples" in output
    assert "Against 2 hand labels" in output


@pytest.mark.parametrize(
    ("backend_name", "extra_arguments", "reason"),
    [
        ("librosa", [], "librosa backend"),
        (TEACHER_BACKEND_NAME, [], "holds no vectors"),
        (TEACHER_BACKEND_NAME, ["--vocabulary", "absent.txt"], "cannot be read"),
    ],
    ids=("another backend", "no vectors", "a missing vocabulary file"),
)
def test_a_scoring_that_cannot_start_ends_with_one_message(
    backend_name: str,
    extra_arguments: list[str],
    reason: str,
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    if extra_arguments:
        source = seed_listening_experiment(connection)
    else:
        source = PostgresExperimentRepository(connection).create(
            backend_name=backend_name, label=None, params={}, key=None
        )
    extra = [str(tmp_path / argument) if argument.endswith(".txt") else argument for argument in extra_arguments]

    with pytest.raises(SystemExit) as raised:
        main(["--experiment-id", str(source), *extra], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED
    assert reason in capsys.readouterr().err


def test_a_scoring_keeps_no_label_count_outside_its_bounds() -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--experiment-id", "1", "--top", "0"], prog=PROGRAM)

    assert raised.value.code == 2


def test_a_key_files_the_scoring_and_a_later_run_shows_it_again_without_the_model(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    loads: list[str] = []

    def load(*, device: str) -> RecordingTeacher:
        loads.append(device)
        return RecordingTeacher()

    monkeypatch.setattr(cli, "load_teacher", load)
    listing = tmp_path / "labels.txt"
    listing.write_text("\n".join(VOCABULARY), encoding="utf-8")
    source = str(seed_listening_experiment(connection))
    main(["--experiment-id", source, "--vocabulary", str(listing), "--key", "categories-a"], prog=PROGRAM)
    filed = PostgresExperimentRepository(connection).get_by_key("categories-a")
    main(["--experiment-id", source, "--vocabulary", str(listing), "--top", "1"], prog=PROGRAM)
    repository = PostgresSampleLabelSuggestionRepository(connection)
    assert filed is not None
    assert repository.shown_experiment_id() != filed.id

    main(["--experiment-id", source, "--vocabulary", str(listing), "--key", "categories-a"], prog=PROGRAM)

    assert repository.shown_experiment_id() == filed.id
    assert len(loads) == 2


def test_a_key_filed_by_another_scoring_recipe_is_refused(
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
    source = str(seed_listening_experiment(connection))
    main(["--experiment-id", source, "--vocabulary", str(listing), "--key", "categories-a"], prog=PROGRAM)

    with pytest.raises(SystemExit) as raised:
        main(
            ["--experiment-id", source, "--vocabulary", str(listing), "--top", "1", "--key", "categories-a"],
            prog=PROGRAM,
        )

    assert raised.value.code == ExitStatus.REFUSED
    assert "another recipe" in capsys.readouterr().err
