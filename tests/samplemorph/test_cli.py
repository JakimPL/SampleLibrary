from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import soundfile
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
from samplemorph.cli import main
from samplemorph.descriptors.descriptor_shape import DESCRIPTOR_SIZE
from samplemorph.geometry import Anchor, log_frequency_geometry
from samplemorph.listening.pairs import CatalogPair, PairEnd, PairSet, write_pair_set
from samplemorph.model_paths import codec_path, descriptor_path, restorer_path
from samplemorph.model_store import model_path
from samplemorph.partials.presets import PROFILE_PRESETS
from samplemorph.training.descriptor_cache import grid_cache_directory, open_grid_cache
from tests.samplemorph.conftest import harmonic_tone
from tests.samplemorph.listening.conftest import CatalogedTone, seed_labeled_tones

PROGRAM = "samplelibrary morph"
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
        main(["fit"], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED
    assert "Configuration error" in capsys.readouterr().err


def test_an_unknown_canonicalizer_exits_before_the_catalog_is_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Argument parsing runs first, so a bad flag never reaches the database."""
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "does-not-exist.toml"))

    with pytest.raises(SystemExit) as raised:
        main(["fit", "--canonicalizer", "stargazer"], prog=PROGRAM)

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

    main(["fit", "--latent-size", str(LATENT_SIZE), "--model", MODEL_NAME], prog=PROGRAM)

    assert model_path(tmp_path, name=MODEL_NAME).exists()
    assert "Fitted" in capsys.readouterr().out


def test_a_library_smaller_than_the_codec_names_the_latent_size_that_fits(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sample_count = len(_seed_catalog(connection, tmp_path))
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))

    with pytest.raises(SystemExit) as raised:
        main(["fit", "--latent-size", str(sample_count + 1), "--model", MODEL_NAME], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED
    assert f"--latent-size {sample_count} or less" in capsys.readouterr().err
    assert not model_path(tmp_path, name=MODEL_NAME).exists()


def test_rendering_writes_a_listening_set_through_a_fitted_model(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hashes = _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    main(["fit", "--latent-size", str(LATENT_SIZE), "--model", MODEL_NAME], prog=PROGRAM)
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
        ],
        prog=PROGRAM,
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


def test_rendering_a_sample_the_catalog_lacks_says_so_before_any_model_loads(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    hashes = _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))

    with pytest.raises(SystemExit) as raised:
        main(
            [
                "render",
                "--first",
                hashes[0],
                "--second",
                "f" * 64,
                "--model",
                "absent",
                "--output",
                str(tmp_path / "out"),
            ],
            prog=PROGRAM,
        )

    assert raised.value.code == ExitStatus.REFUSED
    assert f"Rendered nothing: the catalog holds no sample {'f' * 64}." in capsys.readouterr().err


def test_a_restorer_is_trained_on_the_catalog_and_rendered_through(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production path from catalog to weights to audio, at the smallest size that still exercises it."""
    hashes = _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    main(["fit", "--latent-size", str(LATENT_SIZE), "--model", MODEL_NAME], prog=PROGRAM)
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
            "--precision",
            "32-true",
            "--device",
            "cpu",
            "--restorer",
            RESTORER_NAME,
            "--no-tracking",
        ],
        prog=PROGRAM,
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
        ],
        prog=PROGRAM,
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
    main(["fit", "--latent-size", str(LATENT_SIZE), "--model", MODEL_NAME], prog=PROGRAM)
    identity_output = tmp_path / "measure-identity"
    model_output = tmp_path / "measure-model"
    named = tmp_path / "probes.txt"
    named.write_text(f"{hashes[0]}\n", encoding="utf-8")

    main(
        ["measure", "--model", "identity", "--vocoder", "pghi", "--samples", "2", "--output", str(identity_output)],
        prog=PROGRAM,
    )
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
        ],
        prog=PROGRAM,
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


def test_training_a_restorer_on_an_axis_the_vocoder_never_reads_is_refused_by_the_flags(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["train-restorer", "--canonicalizer", "mel", "--workers", "0", "--device", "cpu"], prog=PROGRAM)

    assert raised.value.code == 2
    assert "invalid choice: 'mel'" in capsys.readouterr().err


def test_rendering_through_a_restorer_that_was_never_trained_says_so(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hashes = _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    main(["fit", "--latent-size", str(LATENT_SIZE), "--model", MODEL_NAME], prog=PROGRAM)

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
            ],
            prog=PROGRAM,
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
        ],
        prog=PROGRAM,
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
        ],
        prog=PROGRAM,
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
        ],
        prog=PROGRAM,
    )

    assert codec_path(tmp_path, name=CODEC_NAME).exists()
    assert (output / "morph_050.wav").exists()
    assert json.loads((output / "manifest.json").read_text())["model"]["codec"] == "conditioned"


def test_measuring_with_no_probe_ends_before_any_model_loads(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    empty = tmp_path / "hashes.txt"
    empty.write_text("\n", encoding="utf-8")

    with pytest.raises(SystemExit) as raised:
        main(["measure", "--model", "absent", "--hashes", str(empty), "--output", str(tmp_path / "out")], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED
    assert "No probe to measure" in capsys.readouterr().err


def test_fitting_over_a_library_with_no_eligible_sample_says_so(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))

    with pytest.raises(SystemExit) as raised:
        main(["fit", "--model", MODEL_NAME], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED
    reported = capsys.readouterr().err
    assert "No sample lies between" in reported
    assert "--latent-size" not in reported


def test_continuing_a_training_run_that_never_ran_ends_with_one_message(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))

    with pytest.raises(SystemExit) as raised:
        main(["train-restorer", "--resume", "--workers", "0", "--device", "cpu", "--no-tracking"], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED
    assert "Trained nothing: --resume continues from" in capsys.readouterr().err


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
            ["train-descriptor", "--cache", "small-teacher", "--teacher-experiment", str(teacher_id), "--no-tracking"],
            prog=PROGRAM,
        )

    assert raised.value.code == ExitStatus.REFUSED
    assert "vectors of 3 numbers" in capsys.readouterr().err


LISTENED_PIANO_COUNT = 5
LISTENED_TONES = tuple(
    CatalogedTone(suggested_label="CHORD", score=0.1, module_index=index, hand_label="PIANO", audible=True)
    for index in range(LISTENED_PIANO_COUNT)
)
COMPARED_WEIGHTS = ("0", "0.5", "1")


def _drawn_pairs(tmp_path: Path) -> Path:
    pairs = tmp_path / "pairs.json"
    main(["draw-pairs", "--seed", "3", "--output", str(pairs)], prog=PROGRAM)
    return pairs


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_drawn_pairs_are_rendered_through_every_route_and_read(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_labeled_tones(connection, tmp_path, LISTENED_TONES)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    main(["fit", "--latent-size", "2", "--model", MODEL_NAME], prog=PROGRAM)
    pairs = _drawn_pairs(tmp_path)
    output = tmp_path / "compared"

    main(
        [
            "compare",
            "--pairs",
            str(pairs),
            "--output",
            str(output),
            "--model",
            MODEL_NAME,
            "--vocoder",
            "pghi",
            "--weights",
            *COMPARED_WEIGHTS,
            "--listening-weights",
            "0.5",
            "--profiles",
            "glide",
            "crossfade",
        ],
        prog=PROGRAM,
    )

    names = [pair["name"] for pair in json.loads(pairs.read_text(encoding="utf-8"))["pairs"]]
    retuned = [
        pair["name"] for pair in json.loads(pairs.read_text(encoding="utf-8"))["pairs"] if pair["kind"] == "retuned"
    ]
    routes = ("latent", "transport", "blend", "partials-glide", "partials-crossfade")
    for name in names:
        assert (output / name / "original_first.wav").exists()
        for route in routes:
            written = sorted(file.name for file in (output / name / route).glob("*.wav"))
            assert written == ["morph_000.wav", "morph_050.wav", "morph_100.wav", "path.wav"]
    readings = _rows(output / "readings.csv")
    assert len(readings) == len(names) * len(routes) * len(COMPARED_WEIGHTS)
    assert retuned
    assert all(
        row["transposition_distance_db"] != "" for row in readings if row["pair"] in retuned and row["weight"] == "0.5"
    )
    assert len(_rows(output / "paths.csv")) == len(_rows(output / "verdicts.csv")) == len(names) * len(routes)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))["routes"]
    assert set(manifest) == set(routes)
    for profile in ("glide", "crossfade"):
        assert manifest[f"partials-{profile}"]["profile"] == PROFILE_PRESETS[profile].model_dump(mode="json")


def test_a_blind_comparison_names_the_routes_by_letter_and_keeps_the_key(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_labeled_tones(connection, tmp_path, LISTENED_TONES)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    pairs = _drawn_pairs(tmp_path)
    output = tmp_path / "blind"

    main(
        [
            "compare",
            "--pairs",
            str(pairs),
            "--output",
            str(output),
            "--routes",
            "transport",
            "blend",
            "--weights",
            *COMPARED_WEIGHTS,
            "--listening-weights",
            "0.5",
            "--blind",
        ],
        prog=PROGRAM,
    )

    key = json.loads((output / "manifest.json").read_text(encoding="utf-8"))["routes"]
    assert sorted(key) == ["A", "B"]
    assert sorted(route["kind"] for route in key.values()) == ["blend", "transport"]
    assert {row["route"] for row in _rows(output / "verdicts.csv")} == {"A", "B"}


def test_comparing_a_pair_with_a_silent_end_ends_before_any_route_loads(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    audible, silent = seed_labeled_tones(
        connection,
        tmp_path,
        (
            CatalogedTone(suggested_label="PIANO", score=0.5, module_index=0, hand_label=None, audible=True),
            CatalogedTone(suggested_label="PIANO", score=0.5, module_index=1, hand_label=None, audible=False),
        ),
    )
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    pairs = tmp_path / "pairs.json"
    write_pair_set(
        pairs,
        PairSet(
            seed=0,
            experiment_id=0,
            pairs=(
                CatalogPair(
                    name="01-same-piano",
                    first=PairEnd(sample_hash=audible, label="PIANO"),
                    second=PairEnd(sample_hash=silent, label="PIANO"),
                ),
            ),
        ),
    )

    with pytest.raises(SystemExit) as raised:
        main(["compare", "--pairs", str(pairs), "--output", str(tmp_path / "out"), "--model", "absent"], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED
    assert f"Compared nothing: pair 01-same-piano names sample {silent}" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_drawing_from_a_catalog_showing_no_scoring_says_so(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_catalog(connection, tmp_path)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))

    with pytest.raises(SystemExit) as raised:
        main(["draw-pairs", "--output", str(tmp_path / "pairs.json")], prog=PROGRAM)

    assert raised.value.code == ExitStatus.REFUSED
    assert "Drew nothing: the catalog shows no label scoring" in capsys.readouterr().err


def test_comparing_pairs_off_a_rising_path_ends_before_any_sample_is_read(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seed_labeled_tones(connection, tmp_path, LISTENED_TONES)
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    pairs = _drawn_pairs(tmp_path)

    with pytest.raises(SystemExit) as raised:
        main(
            ["compare", "--pairs", str(pairs), "--output", str(tmp_path / "out"), "--weights", "0", "0.5"],
            prog=PROGRAM,
        )

    assert raised.value.code == ExitStatus.REFUSED
    assert "Compared nothing: path weights rise from 0 to 1" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_parsing_a_morph_command_loads_no_network_library() -> None:
    """Every morph command's flags, its help included, are read with torch, lightning and numba left unloaded."""
    probe = (
        "import sys, samplemorph.cli; " "sys.exit(any(name in sys.modules for name in ('torch', 'lightning', 'numba')))"
    )

    finished = subprocess.run(
        [sys.executable, "-c", probe], env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, check=False
    )

    assert finished.returncode == 0
