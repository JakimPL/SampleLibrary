from __future__ import annotations

import importlib.util
import tomllib
import types
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE, DATABASE_URL_ENVIRONMENT_VARIABLE, DEFAULT_INFERENCE_URL
from samplecore.hashing import compute_module_hash
from samplecore.storage.sample_audio import SampleAudio
from sampleextract.discovery import FORMAT_LOADERS
from sampleextract.equivalence.detect import detect_equivalences
from sampleextract.files.discovery import discover_sample_files
from sampleextract.ingest import ingest_module
from sampleextract.parsing import parse_module

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "build_dev_library.py"
SANDBOX_DATABASE_URL = "postgresql+psycopg://samplelibrary:samplelibrary@localhost:5432/samplelibrary_dev"
LIBRARY_ON_ANOTHER_PORT = "postgresql+psycopg://someone:secret@localhost:5433/my_library"


def _load_build_dev_library() -> types.ModuleType:
    """Imports the script by file path -- it lives outside every installed package, by design."""
    spec = importlib.util.spec_from_file_location("build_dev_library", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_dev_library = _load_build_dev_library()


def _ingest_all(connection: Connection, library_root: Path, modules_directory: Path) -> None:
    for path in sorted(modules_directory.iterdir()):
        data = path.read_bytes()
        song = parse_module(data, tracker=FORMAT_LOADERS[path.suffix.lower()])
        ingest_module(
            connection,
            library_root,
            module_hash=compute_module_hash(data),
            tracker=FORMAT_LOADERS[path.suffix.lower()],
            filename=path.name,
            file_size=len(data),
            song=song,
            ingested_at=datetime.now(UTC),
            minimum_sample_frames=512,
        )


def test_build_dev_library_writes_every_scenario_module_and_a_config(tmp_path: Path) -> None:
    written_paths = build_dev_library.build_dev_library(tmp_path, database_url=SANDBOX_DATABASE_URL)

    assert len(written_paths) == len(build_dev_library._all_modules())
    assert (tmp_path / "config.toml").is_file()


def test_build_dev_library_config_names_the_database_and_an_inference_address_of_its_own(tmp_path: Path) -> None:
    build_dev_library.build_dev_library(tmp_path, database_url=LIBRARY_ON_ANOTHER_PORT)

    with (tmp_path / "config.toml").open("rb") as config_file:
        config = tomllib.load(config_file)

    assert config["library"]["database_url"] == LIBRARY_ON_ANOTHER_PORT
    assert config["inference"]["url"] != DEFAULT_INFERENCE_URL


def test_the_sandbox_shares_the_configured_server_under_a_database_of_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[library]\n"
        f'module_source_directory = "{(tmp_path / "modules").as_posix()}"\n'
        f'library_root = "{(tmp_path / "library").as_posix()}"\n'
        f'database_url = "{LIBRARY_ON_ANOTHER_PORT}"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))
    monkeypatch.delenv(DATABASE_URL_ENVIRONMENT_VARIABLE, raising=False)

    build_dev_library.main(["--output", str(tmp_path / "sandbox"), "--target-module-count", "13"])

    with (tmp_path / "sandbox" / "config.toml").open("rb") as config_file:
        sandbox_url = tomllib.load(config_file)["library"]["database_url"]
    assert sandbox_url == "postgresql+psycopg://someone:secret@localhost:5433/samplelibrary_dev"


def test_build_dev_library_regenerating_replaces_rather_than_accumulates_modules(tmp_path: Path) -> None:
    first_paths = build_dev_library.build_dev_library(tmp_path, database_url=SANDBOX_DATABASE_URL)

    second_paths = build_dev_library.build_dev_library(tmp_path, database_url=SANDBOX_DATABASE_URL)

    assert len(second_paths) == len(first_paths)


@pytest.mark.parametrize(
    ("relation_type", "expected_count"),
    [("bit_depth_variant", 1), ("amplification_variant", 3), ("resampled_variant", 1)],
)
def test_the_generated_corpus_yields_exactly_the_intended_relations(
    connection: Connection, tmp_path: Path, relation_type: str, expected_count: int
) -> None:
    """A regression check on the corpus itself: every scenario must survive both candidate
    generation and scoring, and no two scenarios may coincidentally relate to each other.
    """
    build_dev_library.build_dev_library(tmp_path, database_url=SANDBOX_DATABASE_URL)
    _ingest_all(connection, tmp_path / "catalog", tmp_path / "modules")

    summary = detect_equivalences(connection, SampleAudio.from_catalog(connection, tmp_path / "catalog"))

    counts = {
        "bit_depth_variant": summary.bit_depth_relations,
        "amplification_variant": summary.amplification_relations,
        "resampled_variant": summary.resampled_relations,
    }
    assert counts[relation_type] == expected_count


def test_the_sandbox_config_names_a_sample_pack_whose_loop_its_exclusions_leave_out(tmp_path: Path) -> None:
    build_dev_library.build_dev_library(tmp_path, database_url=SANDBOX_DATABASE_URL)
    with (tmp_path / "config.toml").open("rb") as config_file:
        library = tomllib.load(config_file)["library"]

    discovery = discover_sample_files(
        tuple(Path(directory) for directory in library["sample_directories"]),
        exclusions=tuple(library["sample_exclusions"]),
    )

    assert [location.relative_path for location in discovery.locations] == [
        "Drums/Kick 01.wav",
        "Drums/Snare 01.wav",
        "Tonal/Pad C.flac",
    ]
