from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import duckdb
import numpy as np
from numpy.typing import NDArray


def read_features(path: Path) -> dict[str, NDArray[np.float64]]:
    """Read every feature vector currently in the store, keyed by sample hash.

    An empty result is returned when the store does not exist yet, rather than raising -- a fresh
    library has extracted nothing yet, which is an ordinary starting state, not an error.
    """
    if not path.is_file():
        return {}

    with duckdb.connect(":memory:") as connection:
        rows = connection.execute("SELECT sample_hash, feature_vector FROM read_parquet(?)", [str(path)]).fetchall()
    return {sample_hash: np.array(feature_vector, dtype=np.float64) for sample_hash, feature_vector in rows}


def write_features(path: Path, features: Mapping[str, NDArray[np.float64]]) -> None:
    """Replace the feature store with exactly the given vectors, one row per sample hash.

    Writing the whole store in one pass, rather than appending, keeps a rerun's merge logic (skip
    hashes already extracted, add the rest) explicit in the caller rather than split across two
    read paths -- this module only ever writes a complete, self-consistent snapshot.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(":memory:") as connection:
        connection.execute("CREATE TABLE features (sample_hash VARCHAR, feature_vector DOUBLE[])")
        if features:
            connection.executemany(
                "INSERT INTO features VALUES (?, ?)",
                [(sample_hash, vector.tolist()) for sample_hash, vector in features.items()],
            )
        connection.execute("COPY features TO ? (FORMAT PARQUET)", [str(path)])
