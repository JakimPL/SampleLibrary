from __future__ import annotations

from pathlib import Path

import numpy as np

from samplecloud.feature_store import read_features, write_features

SAMPLE_HASH_A = "a" * 64
SAMPLE_HASH_B = "b" * 64


def test_reading_a_missing_store_returns_nothing(tmp_path: Path) -> None:
    assert read_features(tmp_path / "features.parquet") == {}


def test_written_vectors_round_trip_exactly(tmp_path: Path) -> None:
    path = tmp_path / "features.parquet"
    features = {
        SAMPLE_HASH_A: np.array([1.0, 2.0, 3.0]),
        SAMPLE_HASH_B: np.array([4.0, 5.0, 6.0]),
    }

    write_features(path, features)

    round_tripped = read_features(path)
    assert round_tripped.keys() == features.keys()
    for sample_hash, vector in features.items():
        np.testing.assert_array_equal(round_tripped[sample_hash], vector)


def test_writing_replaces_the_previous_contents(tmp_path: Path) -> None:
    path = tmp_path / "features.parquet"
    write_features(path, {SAMPLE_HASH_A: np.array([1.0])})

    write_features(path, {SAMPLE_HASH_B: np.array([2.0])})

    assert read_features(path).keys() == {SAMPLE_HASH_B}
