from __future__ import annotations

import importlib.util
import types
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecore.hashing import compute_module_hash
from sampleextract.discovery import FORMAT_LOADERS
from sampleextract.equivalence.detect import detect_equivalences
from sampleextract.ingest import ingest_module
from sampleextract.parsing import parse_module

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "build_dev_library.py"


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
    written_paths = build_dev_library.build_dev_library(tmp_path)

    assert len(written_paths) == len(build_dev_library._all_modules())
    assert (tmp_path / "config.toml").is_file()


def test_build_dev_library_regenerating_replaces_rather_than_accumulates_modules(tmp_path: Path) -> None:
    first_paths = build_dev_library.build_dev_library(tmp_path)

    second_paths = build_dev_library.build_dev_library(tmp_path)

    assert len(second_paths) == len(first_paths)


@pytest.mark.parametrize(
    ("relation_type", "expected_count"),
    [("bit_depth_variant", 1), ("amplification_variant", 3), ("resampled_variant", 2)],
)
def test_the_generated_corpus_yields_exactly_the_intended_relations(
    connection: Connection, tmp_path: Path, relation_type: str, expected_count: int
) -> None:
    """A regression check on the corpus itself: every scenario must survive both candidate
    generation and scoring, and no two scenarios may coincidentally relate to each other.
    """
    build_dev_library.build_dev_library(tmp_path)
    _ingest_all(connection, tmp_path / "catalog", tmp_path / "modules")

    summary = detect_equivalences(connection, tmp_path / "catalog")

    counts = {
        "bit_depth_variant": summary.bit_depth_relations,
        "amplification_variant": summary.amplification_relations,
        "resampled_variant": summary.resampled_relations,
    }
    assert counts[relation_type] == expected_count
