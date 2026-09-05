from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecore.storage.database import connect


@pytest.fixture
def connection() -> Iterator[Connection]:
    open_connection = connect(Path(":memory:"))
    yield open_connection
    open_connection.close()
