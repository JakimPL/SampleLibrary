from __future__ import annotations

from collections.abc import Iterator

import duckdb
import pytest

from samplecore.storage.database import create_schema


@pytest.fixture
def connection() -> Iterator[duckdb.DuckDBPyConnection]:
    open_connection = duckdb.connect(":memory:")
    create_schema(open_connection)
    yield open_connection
    open_connection.close()
