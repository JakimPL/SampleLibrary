from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Column, MetaData, String, Table, create_engine, func, insert, select, text
from sqlalchemy.types import ARRAY, Double

_metadata = MetaData()
_features = Table("features", _metadata, Column("sample_hash", String), Column("feature_vector", ARRAY(Double)))


def read_features(path: Path) -> dict[str, NDArray[np.float64]]:
    """Read every feature vector currently in the store, keyed by sample hash.

    An empty result is returned when the store does not exist yet, rather than raising -- a fresh
    library has extracted nothing yet, which is an ordinary starting state, not an error.
    """
    if not path.is_file():
        return {}

    with create_engine("duckdb:///:memory:").connect() as connection:
        table = func.read_parquet(str(path)).table_valued("sample_hash", "feature_vector")
        rows = connection.execute(select(table.c.sample_hash, table.c.feature_vector)).fetchall()

    return {row.sample_hash: np.array(row.feature_vector, dtype=np.float64) for row in rows}


def write_features(path: Path, features: Mapping[str, NDArray[np.float64]]) -> None:
    """Replace the feature store with exactly the given vectors, one row per sample hash.

    Writing the whole store in one pass, rather than appending, keeps a rerun's merge logic (skip
    hashes already extracted, add the rest) explicit in the caller rather than split across two
    read paths -- this module only ever writes a complete, self-consistent snapshot. The snapshot
    is written to a sibling temporary file first and moved into place afterward, so a run
    interrupted mid-write leaves the previous, complete snapshot on disk rather than a truncated
    file a later read would fail on -- this matters more now that a long extraction run checkpoints
    here repeatedly rather than only once at the end.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.parent / f"{path.name}.tmp"
    with create_engine("duckdb:///:memory:").connect() as connection:
        _metadata.create_all(connection)
        if features:
            connection.execute(
                insert(_features),
                [
                    {"sample_hash": sample_hash, "feature_vector": vector.tolist()}
                    for sample_hash, vector in features.items()
                ],
            )
        # DuckDB's COPY ... TO ... (FORMAT PARQUET) is a vendor-specific bulk-export command with
        # no relational-algebra equivalent for Core to build, so it stays a narrow, parameterized
        # text() fragment rather than forcing a construct that does not exist.
        connection.execute(text("COPY features TO :path (FORMAT PARQUET)"), {"path": str(temporary_path)})
    temporary_path.replace(path)
