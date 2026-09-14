from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecloud.cli import main
from samplecloud.experiments import EmbeddingRecipe
from samplecloud.registries import DEFAULT_BACKEND_NAME
from samplecloud.run import create_experiment
from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from samplecore.exit_status import ExitStatus
from samplecore.models.channels import ChannelLayout
from samplecore.models.experiment import Reading
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.repositories.cloud import PostgresCloudPromotionRepository
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository

PROGRAM = "samplelibrary cloud embed"
SAMPLE_HASH = "a" * 64


def _write_config(tmp_path: Path, database_url: str) -> Path:
    """Points both configured paths at `tmp_path` itself, which always exists -- this CLI only
    ever reads a catalog and audio store an extraction run has already populated.
    """
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[library]\nmodule_source_directory = "{tmp_path.as_posix()}"\nlibrary_root = "{tmp_path.as_posix()}"\n'
        f'database_url = "{database_url}"\n',
        encoding="utf-8",
    )
    return config_path


def test_main_reports_a_configuration_error_and_exits_without_a_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "does-not-exist.toml"))

    with pytest.raises(SystemExit) as raised:
        main([], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED
    assert "Configuration error" in capsys.readouterr().err


def test_main_reports_an_empty_catalog(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))

    main([], prog=PROGRAM)

    output = capsys.readouterr().out
    assert "extracted features for 0 new samples" in output
    assert "Reduced 0 samples" in output


def test_main_passes_the_limit_argument_through(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    sample = Sample(hash=SAMPLE_HASH, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=32)
    PostgresSampleRepository(connection).upsert(sample)
    audio_store.write(tmp_path, SamplePCM(sample=sample, pcm=np.zeros((32, 1))))
    connection.commit()

    main(["--limit", "1", "--extract-only"], prog=PROGRAM)

    assert "extracted features for 1 new samples" in capsys.readouterr().out


def test_main_rejects_an_unknown_backend(capsys: pytest.CaptureFixture[str]) -> None:
    """Argument parsing rejects an unknown --backend before any config or database is touched."""
    with pytest.raises(SystemExit):
        main(["--backend", "does-not-exist"], prog=PROGRAM)

    assert "invalid choice" in capsys.readouterr().err


def _refusal(raised: pytest.ExceptionInfo[SystemExit], capsys: pytest.CaptureFixture[str]) -> str:
    assert raised.value.code == ExitStatus.REFUSED
    captured = capsys.readouterr()
    return captured.out + captured.err


def test_a_rebuild_of_an_empty_cloud_starts_and_shows_the_default_experiment(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))

    main(["--resume-promoted"], prog=PROGRAM)

    promotion = PostgresCloudPromotionRepository(connection).current()
    assert promotion is not None
    experiment = PostgresExperimentRepository(connection).get(promotion.experiment_id)
    assert experiment is not None
    assert experiment.backend_name == DEFAULT_BACKEND_NAME


@pytest.mark.parametrize(
    "flags",
    [["--backend", "invariant"], ["--heard-rate"], ["--extract-only"], ["--label", "again"]],
    ids=("a backend", "a reading", "an unshown pass", "a label"),
)
def test_a_rebuild_takes_no_flag_it_settles_itself(
    flags: list[str],
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))

    with pytest.raises(SystemExit) as raised:
        main(["--resume-promoted", *flags], prog=PROGRAM)

    assert flags[0] in _refusal(raised, capsys)
    assert PostgresCloudPromotionRepository(connection).current() is None


@pytest.mark.parametrize(
    "flags",
    [["--backend", "invariant"], ["--model", "descriptor"], ["--heard-rate"], ["--label", "again"]],
    ids=("another backend", "a model", "another reading", "a label"),
)
def test_resuming_an_experiment_refuses_flags_naming_another_recipe(
    flags: list[str],
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    experiment_id = create_experiment(
        connection,
        EmbeddingRecipe(backend_name=DEFAULT_BACKEND_NAME, reading=Reading.NOMINAL, model_name=None),
        label=None,
        key=None,
    )

    with pytest.raises(SystemExit) as raised:
        main(["--experiment-id", str(experiment_id), *flags], prog=PROGRAM)

    assert flags[0] in _refusal(raised, capsys)


def test_resuming_an_experiment_accepts_flags_repeating_its_recipe(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    experiment_id = create_experiment(
        connection,
        EmbeddingRecipe(backend_name=DEFAULT_BACKEND_NAME, reading=Reading.NOMINAL, model_name=None),
        label=None,
        key=None,
    )

    main(["--experiment-id", str(experiment_id), "--backend", DEFAULT_BACKEND_NAME, "--extract-only"], prog=PROGRAM)

    assert f"Experiment {experiment_id}: extracted features for 0 new samples" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("flags", "reason"),
    [
        (["--experiment-id", "999999"], "holds no experiment 999999"),
        (["--backend", "learned"], "needs --model"),
        (["--model", "descriptor"], "learned backend reads"),
    ],
    ids=("an unknown experiment", "a learned backend naming no model", "a model with another backend"),
)
def test_a_request_naming_no_embeddable_experiment_ends_with_one_message(
    flags: list[str],
    reason: str,
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    experiments_before = PostgresExperimentRepository(connection).next_id()

    with pytest.raises(SystemExit) as raised:
        main(flags, prog=PROGRAM)

    reported = _refusal(raised, capsys)
    assert reason in reported
    assert "Traceback" not in reported
    assert PostgresExperimentRepository(connection).get(experiments_before + 1) is None


def test_a_rebuild_and_a_named_experiment_are_one_choice() -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--resume-promoted", "--experiment-id", "1"], prog=PROGRAM)

    assert raised.value.code == 2


def _catalog_tone(connection: Connection, library_root: Path, sample_hash: str, *, frequency: float) -> None:
    frames = 4096
    sample = Sample(hash=sample_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=frames)
    tone = 0.5 * np.sin(2 * np.pi * frequency * np.arange(frames) / audio_store.NOMINAL_WAV_RATE)
    PostgresSampleRepository(connection).upsert(sample)
    audio_store.write(library_root, SamplePCM(sample=sample, pcm=tone.reshape(-1, 1)))
    connection.commit()


def test_a_key_files_the_first_run_s_experiment_and_every_later_run_resumes_it(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    _catalog_tone(connection, tmp_path, SAMPLE_HASH, frequency=440.0)
    main(["--backend", "librosa", "--key", "librosa-nominal", "--extract-only"], prog=PROGRAM)
    filed = PostgresExperimentRepository(connection).get_by_key("librosa-nominal")
    _catalog_tone(connection, tmp_path, "b" * 64, frequency=660.0)
    capsys.readouterr()

    main(["--backend", "librosa", "--key", "librosa-nominal", "--extract-only"], prog=PROGRAM)

    assert filed is not None
    assert PostgresExperimentRepository(connection).get_by_key("librosa-nominal") == filed
    assert f"Experiment {filed.id}: extracted features for 1 new samples (1 already known" in capsys.readouterr().out
    assert PostgresCloudPromotionRepository(connection).current() is None


def test_a_key_filed_by_another_recipe_is_refused(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    main(["--backend", "librosa", "--key", "descriptor", "--extract-only"], prog=PROGRAM)

    with pytest.raises(SystemExit) as raised:
        main(["--backend", "invariant", "--key", "descriptor", "--extract-only"], prog=PROGRAM)

    assert "--backend invariant" in _refusal(raised, capsys)


def test_a_key_names_the_experiment_in_place_of_an_id(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--key", "teacher", "--experiment-id", "1"], prog=PROGRAM)

    assert raised.value.code == ExitStatus.USAGE
    assert "not allowed with argument" in capsys.readouterr().err
