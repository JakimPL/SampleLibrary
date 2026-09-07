from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from fastapi import Request
from sqlalchemy import Connection

from samplecore.storage.database import connect


def get_library_root(request: Request) -> Path:
    """The content-addressable audio store's root, for routes that read a sample's own bytes."""
    return Path(request.app.state.library_root)


def get_connection(request: Request) -> Iterator[Connection]:
    """A fresh read-only connection to the app's configured catalog, closed after the request.

    A single SQLAlchemy ``Connection`` is not safe to use concurrently from the thread pool
    FastAPI's synchronous route handlers run in -- opening one per request sidesteps that entirely,
    at a cost negligible next to an HTTP round trip at this project's personal-library scale.
    Postgres itself handles many concurrent connections natively, so this per-request pattern needs
    no extra coordination to stay safe.
    """
    connection = connect(request.app.state.database_url, read_only=True)
    try:
        yield connection
    finally:
        connection.close()
