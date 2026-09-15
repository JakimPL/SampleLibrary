from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from pathlib import Path

TableValue = str | int | float | bool


def write_table(path: Path, rows: Sequence[Mapping[str, TableValue]]) -> None:
    """Write rows sharing one set of columns as a CSV file with a header, the columns in the first row's order.

    Raises:
        ValueError: there are no rows, leaving no columns to name.
    """
    if not rows:
        raise ValueError(f"a table at {path} needs at least one row to name its columns")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
