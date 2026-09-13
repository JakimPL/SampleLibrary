from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Final

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from samplecore.storage.database import connect_for_curation, create_pooled_engine
from sampleserver.frontend import SinglePageApplication
from sampleserver.inference_client import build_inference_client
from sampleserver.response_cache import RevisionedJsonCache
from sampleserver.routers import cloud, curation, modules, morph, samples, stats
from sampleserver.spectral_cache import SpectralVectorCache

API_PREFIX: Final[str] = "/api"
GZIP_MINIMUM_SIZE: Final[int] = 1024
GZIP_COMPRESSION_LEVEL: Final[int] = 1
READ_POOL_SIZE: Final[int] = 5


def create_app(
    database_url: str, library_root: Path, inference_url: str, *, frontend_directory: Path | None
) -> FastAPI:
    """Build the FastAPI app serving the catalog at the given database URL.

    Every route reads the catalog through a pooled connection Postgres itself refuses a write on. The
    curation routes are the one exception, and they reach only a person's own decisions about
    samples, in a schema of their own: what this application records is what a listener decided, and
    the catalog stays the offline pipelines' to build. Morphs are rendered by a separate inference
    process at `inference_url`, which the morph routes reach over HTTP, so the models and the
    libraries behind them stay out of this process.

    Every route is served under `API_PREFIX`, which keeps the whole API inside one path segment
    the single-page application's own routes stay clear of: the frontend reaches `/api/samples`
    while a person's browser holds `/samples/{hash}`, so one path always names one thing. A
    response past a kilobyte goes out gzipped when the caller accepts it: the cloud's hundred
    thousand points are text that compresses several-fold, and the lightest level costs a fraction
    of a second per request against tens of megabytes saved on the wire; audio and byte ranges
    pass through as they are.

    A pure factory, deliberately without any module-level instance built from real
    configuration -- that belongs to `sampleserver.main`, the actual ASGI entry point, so that
    importing this module (as tests do, to build an app over a temporary catalog) never depends
    on a real `config.toml` existing. The connections this factory arranges are opened at startup
    rather than at build time, for the same reason.
    """

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Prepare the curation schema, the catalog's pool and the inference client before the first request.

        The samples listing reads a sample's hand annotation as part of its own query, and the
        read-only connection every route uses can create nothing. Preparing the schema once at
        startup is what lets a database the offline pipelines have never written to still serve a
        listing. The pool and the inference client live as long as the app, so their connections
        are reused across requests, and both are closed when the app stops.
        """
        connect_for_curation(application.state.database_url).close()
        application.state.engine = create_pooled_engine(application.state.database_url, pool_size=READ_POOL_SIZE)
        application.state.inference_client = build_inference_client(application.state.inference_url)
        try:
            yield
        finally:
            await application.state.inference_client.aclose()
            application.state.engine.dispose()

    application = FastAPI(
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=f"{API_PREFIX}/redoc",
        title="SampleLibrary",
        description="Read access to the sample catalog, with hand annotation and morphs between samples.",
        lifespan=lifespan,
    )
    application.add_middleware(GZipMiddleware, minimum_size=GZIP_MINIMUM_SIZE, compresslevel=GZIP_COMPRESSION_LEVEL)
    application.state.database_url = database_url
    application.state.library_root = library_root
    application.state.inference_url = inference_url
    application.state.spectral_vectors = SpectralVectorCache()
    application.state.cloud_cache = RevisionedJsonCache()
    application.state.suggestions_cache = RevisionedJsonCache()
    for api_router in (modules.router, samples.router, stats.router, cloud.router, curation.router, morph.router):
        application.include_router(api_router, prefix=API_PREFIX)
    if frontend_directory is not None:
        application.mount("/", SinglePageApplication(frontend_directory, api_prefix=API_PREFIX), name="frontend")
    return application
