from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import soundfile
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth
from trackmod.trackers.xm.tuning import Tuning

from samplecloud.run import resolve_experiment
from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
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
from samplemorph.cli import main
from samplemorph.codecs.conditioned import codec_path
from samplemorph.descriptors.grid_descriptor import DESCRIPTOR_SIZE
from samplemorph.descriptors.learned import descriptor_path
from samplemorph.geometry import Anchor, log_frequency_geometry
from samplemorph.model_store import model_path
from samplemorph.training.descriptor_cache import grid_cache_directory, open_grid_cache
from samplemorph.vocoders.restored import restorer_path
from tests.samplemorph.conftest import harmonic_tone

SAMPLE_FRAME_COUNT = 4096
CATALOG_SIZE = 12
LATENT_SIZE = 4
SAMPLE_RATE_HZ = 8_363
MODEL_NAME = "under-test"
DESCRIPTOR_NAME = "descriptor-under-test"
CODEC_NAME = "codec-under-test"
RESTORER_NAME = "restorer-under-test"
RESTORER_CHANNELS = 8
RESTORER_CROP_FRAMES = 8


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
        main(["fit"])

    assert raised.value.code == 1
    assert "Configuration error" in capsys.readouterr().err


def test_an_unknown_canonicalizer_exits_before_the_catalog_is_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Argument parsing runs first, so a bad flag never reaches the database."""
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "does-not-exist.toml"))

    with pytest.raises(SystemExit) as raised:
        main(["fit", "--canonicalizer", "stargazer"])

    assert raised.value.code == 2


def test_fitting_writes_a_model_under_the_library_root(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))

    main(["fit", "--canonicalizer", "mel", "--latent-size", str(LATENT_SIZE), "--model", MODEL_NAME])

    assert model_path(tmp_path, name=MODEL_NAME).exists()
    assert "Fitted" in capsys.readouterr().out


def test_rendering_writes_a_listening_set_through_a_fitted_model(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hashes = _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    main(["fit", "--latent-size", str(LATENT_SIZE), "--model", MODEL_NAME])
    output = tmp_path / "render"

    main(
        [
            "render",
            "--first",
            hashes[0],
            "--second",
            hashes[-1],
            "--model",
            MODEL_NAME,
            "--vocoder",
            "pghi",
            "--output",
            str(output),
        ]
    )

    written = sorted(path.name for path in output.glob("*.wav"))
    assert written == [
        "morph_025.wav",
        "morph_050.wav",
        "morph_075.wav",
        "original_first.wav",
        "original_second.wav",
        "reconstruction_first.wav",
        "reconstruction_second.wav",
    ]
    assert (output / "manifest.json").exists()
    assert soundfile.info(output / "original_first.wav").samplerate == SAMPLE_RATE_HZ


def test_rendering_a_sample_the_catalog_lacks_says_so(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hashes = _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    main(["fit", "--canonicalizer", "mel", "--latent-size", str(LATENT_SIZE), "--model", MODEL_NAME])

    with pytest.raises(ValueError, match="holds no sample"):
        main(
            [
                "render",
                "--first",
                hashes[0],
                "--second",
                "f" * 64,
                "--model",
                MODEL_NAME,
                "--output",
                str(tmp_path / "render"),
            ]
        )


def test_a_restorer_is_trained_on_the_catalog_and_rendered_through(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production path from catalog to weights to audio, at the smallest size that still exercises it."""
    hashes = _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    main(["fit", "--latent-size", str(LATENT_SIZE), "--model", MODEL_NAME])
    main(
        [
            "train-restorer",
            "--epochs",
            "1",
            "--batch",
            "2",
            "--workers",
            "0",
            "--channels",
            str(RESTORER_CHANNELS),
            "--crop",
            str(RESTORER_CROP_FRAMES),
            "--device",
            "cpu",
            "--restorer",
            RESTORER_NAME,
            "--no-tracking",
        ]
    )
    output = tmp_path / "restored-render"

    main(
        [
            "render",
            "--first",
            hashes[0],
            "--second",
            hashes[-1],
            "--model",
            MODEL_NAME,
            "--restorer",
            RESTORER_NAME,
            "--device",
            "cpu",
            "--output",
            str(output),
        ]
    )

    assert restorer_path(tmp_path, name=RESTORER_NAME).exists()
    assert (output / "morph_050.wav").exists()
    assert soundfile.info(output / "morph_050.wav").frames > 0


def test_probes_are_measured_through_the_representation_and_through_a_fitted_model(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each probe comes back beside its reconstruction at matched loudness, with one row of readings."""
    hashes = _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    main(["fit", "--latent-size", str(LATENT_SIZE), "--model", MODEL_NAME])
    identity_output = tmp_path / "measure-identity"
    model_output = tmp_path / "measure-model"
    named = tmp_path / "probes.txt"
    named.write_text(f"{hashes[0]}\n", encoding="utf-8")

    main(["measure", "--model", "identity", "--vocoder", "pghi", "--samples", "2", "--output", str(identity_output)])
    main(
        [
            "measure",
            "--model",
            MODEL_NAME,
            "--vocoder",
            "pghi",
            "--hashes",
            str(named),
            "--device",
            "cpu",
            "--output",
            str(model_output),
        ]
    )

    identity_folders = sorted(path for path in identity_output.iterdir() if path.is_dir())
    assert len(identity_folders) == 2
    assert all(
        (folder / "original.wav").exists() and (folder / "reconstruction.wav").exists() for folder in identity_folders
    )
    with (identity_output / "readings.csv").open(encoding="utf-8") as handle:
        identity_rows = list(csv.DictReader(handle))
    assert len(identity_rows) == 2
    assert {"hash", "sound_type", "model", "held_out_db", "fluctuation_excess", "peak_dbfs"} <= set(identity_rows[0])
    with (model_output / "readings.csv").open(encoding="utf-8") as handle:
        model_rows = list(csv.DictReader(handle))
    assert [row["hash"] for row in model_rows] == [hashes[0]]
    assert model_rows[0]["model"] == MODEL_NAME
    (model_folder,) = (path for path in model_output.iterdir() if path.is_dir())
    assert model_folder.name.endswith(hashes[0][:12])


def test_training_a_restorer_on_an_axis_the_vocoder_never_reads_says_so(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))

    with pytest.raises(ValueError, match="is a mel one"):
        main(["train-restorer", "--canonicalizer", "mel", "--workers", "0", "--device", "cpu", "--no-tracking"])


def test_rendering_through_a_restorer_that_was_never_trained_says_so(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hashes = _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    main(["fit", "--canonicalizer", "mel", "--latent-size", str(LATENT_SIZE), "--model", MODEL_NAME])

    with pytest.raises(FileNotFoundError, match="no restorer is stored"):
        main(
            [
                "render",
                "--first",
                hashes[0],
                "--second",
                hashes[-1],
                "--model",
                MODEL_NAME,
                "--restorer",
                "absent",
                "--device",
                "cpu",
                "--output",
                str(tmp_path / "render"),
            ]
        )


def test_a_retuned_view_records_its_samples_own_duration(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A view differs from the stored reading in its grid alone, so the duration beside it is the sample's."""
    _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))

    main(["cache-grids", "--cache", "views-under-test", "--views", "2", "--workers", "0"])

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
    teacher_id = resolve_experiment(connection, backend_name="stub", label="teacher")
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

    main(["cache-grids", "--cache", "under-test", "--views", "1", "--workers", "0", "--anchor", "fundamental"])
    main(
        [
            "train-descriptor",
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
        ]
    )
    main(["embed", "--cache", "under-test", "--descriptor", DESCRIPTOR_NAME, "--device", "cpu"])

    cache = open_grid_cache(grid_cache_directory(tmp_path, name="under-test"))
    assert cache.sample_count == CATALOG_SIZE
    assert cache.description.geometry.anchor is Anchor.FUNDAMENTAL
    assert descriptor_path(tmp_path, name=DESCRIPTOR_NAME).exists()
    experiment = PostgresExperimentRepository(connection).get(teacher_id + 1)
    assert experiment is not None
    assert experiment.backend_name == LEARNED_BACKEND_NAME
    assert len(PostgresSampleFeatureVectorRepository(connection).list_for_experiment(experiment.id)) == CATALOG_SIZE

    main(
        [
            "cache-grids",
            "--cache",
            "full",
            "--bands-per-semitone",
            str(round(log_frequency_geometry().bands_per_semitone)),
            "--views",
            "0",
            "--workers",
            "0",
            "--anchor",
            "fundamental",
        ]
    )
    main(
        [
            "train-codec",
            "--cache",
            "full",
            "--descriptor",
            DESCRIPTOR_NAME,
            "--codec",
            CODEC_NAME,
            "--width",
            "4",
            "--residual-size",
            "4",
            "--epochs",
            "1",
            "--batch",
            "4",
            "--workers",
            "0",
            "--device",
            "cpu",
            "--no-tracking",
        ]
    )
    output = tmp_path / "listening"
    main(
        [
            "render",
            "--first",
            hashes[0],
            "--second",
            hashes[1],
            "--output",
            str(output),
            "--model",
            CODEC_NAME,
            "--vocoder",
            "pghi",
            "--device",
            "cpu",
        ]
    )

    assert codec_path(tmp_path, name=CODEC_NAME).exists()
    assert (output / "morph_050.wav").exists()
    assert json.loads((output / "manifest.json").read_text())["model"]["codec"] == "conditioned"
