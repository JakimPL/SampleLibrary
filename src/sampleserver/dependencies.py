from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
from fastapi import Depends, Request
from sqlalchemy import Connection

from samplecore.spectral_distance import SpectralVectors
from samplecore.storage.database import checkout_read_only
from sampleserver.response_cache import RevisionedJsonCache
from sampleserver.spectral_cache import SpectralVectorCache


def get_library_root(request: Request) -> Path:
    """The content-addressable audio store's root, for routes that read a sample's own bytes."""
    return Path(request.app.state.library_root)


def get_inference_client(request: Request) -> httpx.AsyncClient:
    """The client the morph routes reach the inference process through, opened once for the app's lifetime."""
    client: httpx.AsyncClient = request.app.state.inference_client
    return client


def get_connection(request: Request) -> Iterator[Connection]:
    """A read-only connection to the app's configured catalog, checked out of the pool for one request.

    A single SQLAlchemy ``Connection`` is not safe to use concurrently from the thread pool
    FastAPI's synchronous route handlers run in, so each request holds one of its own and returns
    it when done; the pool keeps the connection open for the next request, which is what makes a
    sound or a hover cost a query rather than a handshake. Postgres itself refuses any write on
    the transaction, the same as a role-level grant would.
    """
    connection = checkout_read_only(request.app.state.engine)
    try:
        yield connection
    finally:
        connection.close()


def get_curation_connection(request: Request) -> Iterator[Connection]:
    """A writable connection for the one thing this application records: a person's own labels.

    Every other route reads through `get_connection`, whose transaction Postgres itself refuses a
    write on. This is the single exception, reached only by the routes changing annotations. It is
    checked out of the same pool, the curation schema having been prepared once as the app started;
    the pool clears the read-only rule from a connection as it comes back, so each checkout carries
    only the rule its own dependency sets.
    """
    connection = request.app.state.engine.connect()
    try:
        yield connection
    finally:
        connection.close()


def get_spectral_vectors(request: Request, connection: Connection = Depends(get_connection)) -> SpectralVectors:
    """The catalog's spectral vectors as one matrix, parsed once per embedding rather than per request."""
    cache: SpectralVectorCache = request.app.state.spectral_vectors
    return cache.vectors(connection)


def get_cloud_cache(request: Request) -> RevisionedJsonCache:
    """The finished answer to the cloud's points, kept per application across requests."""
    cache: RevisionedJsonCache = request.app.state.cloud_cache
    return cache


def get_suggestions_cache(request: Request) -> RevisionedJsonCache:
    """The finished answer to the cloud's suggestions, kept per application across requests."""
    cache: RevisionedJsonCache = request.app.state.suggestions_cache
    return cache
