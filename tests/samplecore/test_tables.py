from __future__ import annotations

import csv
from pathlib import Path

import pytest

from samplecore.tables import write_table


def test_a_table_is_written_with_the_first_rows_columns_as_its_header(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "table.csv"

    write_table(path, [{"name": "first", "value": 1.5, "kept": True}, {"name": "second", "value": 2, "kept": False}])

    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [
        {"name": "first", "value": "1.5", "kept": "True"},
        {"name": "second", "value": "2", "kept": "False"},
    ]


def test_a_table_of_no_rows_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_table(tmp_path / "empty.csv", [])
