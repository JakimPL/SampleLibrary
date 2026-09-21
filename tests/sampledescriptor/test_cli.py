from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth
from trackmod.trackers.xm.tuning import Tuning

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from samplecore.exit_status import ExitStatus
from samplecore.models.channels import ChannelLayout
from samplecore.models.experiment import LEARNED_BACKEND_NAME, SampleFeatureVector
from samplecore.models.module import Module
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.models.sample_properties import SampleOccurrence, XMSampleProperties
from samplecore.models.tracker import TrackerFormat
from samplecore.storage import audio_store
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository
from sampledescriptor.cli import main
from sampledescriptor.descriptors.shape import DESCRIPTOR_SIZE
from sampledescriptor.geometry import Anchor
from sampledescriptor.model_paths import descriptor_path
from sampledescriptor.training.descriptor.cache import grid_cache_directory, open_grid_cache
from tests.samplemorph.conftest import harmonic_tone

PROGRAM = "samplelibrary descriptor"
SAMPLE_FRAME_COUNT = 4096
CATALOG_SIZE = 12
SAMPLE_RATE_HZ = 8_363
DESCRIPTOR_NAME = "descriptor-under-test"


def _write_config(tmp_path: Path, database_url: str) -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[library]\nmodule_source_directory = "{tmp_path.as_posix()}"\n'
        f'library_root = "{tmp_path.as_posix()}"\ndatabase_url = "{database_url}"\n',
        encoding="utf-8",
    )
    return config_path


def _seed_catalog(connection: Connection, library_root: Path) -> list[str]:
    """A small catalog of distinct tones, each with one occurrence naming its playback rate.

    A hash repeats one byte, so the prefixes that name files and folders differ between samples.
    """
    module_repository = PostgresModuleRepository(connection)
    hashes = []
    for index in range(CATALOG_SIZE):
        sample = Sample(
            hash=f"{index + 1:02x}" * 32,
            depth=BitDepth.SIXTEEN,
            channels=ChannelLayout.MONO,
            frames=SAMPLE_FRAME_COUNT,
        )
        PostgresSampleRepository(connection).upsert(sample)
        audio_store.write(
            library_root,
            SamplePCM(sample=sample, pcm=harmonic_tone(SAMPLE_FRAME_COUNT, frequency=110.0 * (1.0 + index / 3.0))),
        )
        module = Module(
            id=module_repository.next_id(),
            hash=format(index + 900, "064x"),
            filename=f"song{index}.xm",
            tracker=TrackerFormat.XM,
            title="untitled",
            channel_count=4,
            pattern_count=1,
            instrument_count=1,
            sample_count=1,
            file_size=1024,
            ingested_at=datetime.now(UTC),
        )
        module_repository.insert(module)
        PostgresSamplePropertiesRepository(connection).upsert(
            XMSampleProperties(
                sample_hash=sample.hash,
                occurrence=SampleOccurrence(module_hash=module.hash, instrument_index=0, sample_slot=0),
                name=f"tone{index}",
                rate=SAMPLE_RATE_HZ,
                volume=64,
                tuning=Tuning(relative_note=0, finetune=0),
            )
        )
        hashes.append(sample.hash)
    connection.commit()
    return hashes


def test_main_reports_a_configuration_error_and_exits_without_a_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "does-not-exist.toml"))

    with pytest.raises(SystemExit) as raised:
        main(["cache-grids"], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED
    assert "Configuration error" in capsys.readouterr().err


def test_an_unknown_canonicalizer_exits_before_the_catalog_is_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Argument parsing runs first, so a bad flag never reaches the database."""
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "does-not-exist.toml"))

    with pytest.raises(SystemExit) as raised:
        main(["cache-grids", "--canonicalizer", "stargazer"], prog=PROGRAM)

    assert raised.value.code == 2


def test_a_retuned_view_records_its_samples_own_duration(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A view differs from the stored reading in its grid alone, so the duration beside it is the sample's."""
    _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))

    main(["cache-grids", "--cache", "views-under-test", "--views", "2", "--workers", "0"], prog=PROGRAM)

    cache = open_grid_cache(grid_cache_directory(tmp_path, name="views-under-test"))
    assert cache.durations.shape == (CATALOG_SIZE, 3)
    assert np.array_equal(cache.durations, np.repeat(cache.durations[:, :1], 3, axis=1))
    assert not np.array_equal(cache.grids[:, 0], cache.grids[:, 1])


def test_a_descriptor_goes_from_cache_to_weights_to_an_experiment(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The three passes end to end at the smallest size that still exercises them, on the processor."""
    hashes = _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    teacher_id = PostgresExperimentRepository(connection).create(
        backend_name="stub", label="teacher", params={}, key=None
    )
    generator = np.random.default_rng(0)
    PostgresSampleFeatureVectorRepository(connection).insert_many(
        [
            SampleFeatureVector(
                experiment_id=teacher_id,
                sample_hash=sample_hash,
                vector=tuple(generator.normal(size=DESCRIPTOR_SIZE).tolist()),
                computed_at=datetime.now(UTC),
            )
            for sample_hash in hashes
        ]
    )
    connection.commit()

    main(
        ["cache-grids", "--cache", "under-test", "--views", "1", "--workers", "0", "--anchor", "fundamental"],
        prog=PROGRAM,
    )
    main(
        [
            "train",
            "--cache",
            "under-test",
            "--teacher-experiment",
            str(teacher_id),
            "--descriptor",
            DESCRIPTOR_NAME,
            "--width",
            "4",
            "--epochs",
            "1",
            "--batch",
            "4",
            "--labeled-per-batch",
            "1",
            "--workers",
            "0",
            "--device",
            "cpu",
            "--no-tracking",
        ],
        prog=PROGRAM,
    )
    main(["embed", "--cache", "under-test", "--descriptor", DESCRIPTOR_NAME, "--device", "cpu"], prog=PROGRAM)

    cache = open_grid_cache(grid_cache_directory(tmp_path, name="under-test"))
    assert cache.sample_count == CATALOG_SIZE
    assert cache.description.geometry.anchor is Anchor.FUNDAMENTAL
    assert descriptor_path(tmp_path, name=DESCRIPTOR_NAME).exists()
    experiment = PostgresExperimentRepository(connection).get(teacher_id + 1)
    assert experiment is not None
    assert experiment.backend_name == LEARNED_BACKEND_NAME
    assert len(PostgresSampleFeatureVectorRepository(connection).list_for_experiment(experiment.id)) == CATALOG_SIZE
    keyed = ["embed", "--cache", "under-test", "--descriptor", DESCRIPTOR_NAME, "--device", "cpu", "--key", "learned"]
    main(keyed, prog=PROGRAM)
    filed = PostgresExperimentRepository(connection).get_by_key("learned")
    main(keyed, prog=PROGRAM)
    assert filed is not None
    assert PostgresExperimentRepository(connection).get(filed.id + 1) is None


def test_a_teacher_whose_vectors_a_descriptor_cannot_answer_in_is_refused(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    hashes = _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    teacher_id = PostgresExperimentRepository(connection).create(
        backend_name="librosa", label=None, params={}, key=None
    )
    PostgresSampleFeatureVectorRepository(connection).insert_many(
        [
            SampleFeatureVector(
                experiment_id=teacher_id, sample_hash=sample_hash, vector=(0.1, 0.2, 0.3), computed_at=datetime.now(UTC)
            )
            for sample_hash in hashes
        ]
    )
    connection.commit()
    main(["cache-grids", "--cache", "small-teacher", "--views", "1", "--workers", "0"], prog=PROGRAM)

    with pytest.raises(SystemExit) as raised:
        main(
            ["train", "--cache", "small-teacher", "--teacher-experiment", str(teacher_id), "--no-tracking"],
            prog=PROGRAM,
        )

    assert raised.value.code == ExitStatus.REFUSED
    assert "vectors of 3 numbers" in capsys.readouterr().err


def test_continuing_a_training_run_that_never_ran_ends_with_one_message(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    hashes = _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    teacher_id = PostgresExperimentRepository(connection).create(
        backend_name="stub", label="teacher", params={}, key=None
    )
    PostgresSampleFeatureVectorRepository(connection).insert_many(
        [
            SampleFeatureVector(
                experiment_id=teacher_id,
                sample_hash=sample_hash,
                vector=tuple(np.zeros(DESCRIPTOR_SIZE).tolist()),
                computed_at=datetime.now(UTC),
            )
            for sample_hash in hashes
        ]
    )
    connection.commit()
    main(["cache-grids", "--cache", "never-ran", "--views", "1", "--workers", "0"], prog=PROGRAM)

    with pytest.raises(SystemExit) as raised:
        main(
            [
                "train",
                "--cache",
                "never-ran",
                "--teacher-experiment",
                str(teacher_id),
                "--resume",
                "--workers",
                "0",
                "--device",
                "cpu",
                "--no-tracking",
            ],
            prog=PROGRAM,
        )

    assert raised.value.code == ExitStatus.REFUSED
    assert "Trained nothing: --resume continues from" in capsys.readouterr().err
