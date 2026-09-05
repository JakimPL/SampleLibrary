from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import duckdb
from fastapi import Request


def get_library_root(request: Request) -> Path:
    """The content-addressable audio store's root, for routes that read a sample's own bytes."""
    return Path(request.app.state.library_root)


def get_connection(request: Request) -> Iterator[duckdb.DuckDBPyConnection]:
    """A fresh read-only connection to the app's configured catalog, closed after the request.

    DuckDB's read-only mode is built for concurrent readers, while a single connection is not
    safe to use concurrently from the thread pool FastAPI's synchronous route handlers run in --
    opening one per request sidesteps that entirely, at a cost negligible next to an HTTP round
    trip at this project's personal-library scale.
    """
    connection = duckdb.connect(str(request.app.state.database_path), read_only=True)
    try:
        yield connection
    finally:
        connection.close()
