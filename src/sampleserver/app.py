from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Final

from fastapi import FastAPI

from samplecore.storage.database import connect_for_curation
from sampleserver.inference_client import build_inference_client
from sampleserver.routers import cloud, curation, modules, morph, samples, stats
from sampleserver.spectral_cache import SpectralVectorCache

API_PREFIX: Final[str] = "/api"


def create_app(database_url: str, library_root: Path, inference_url: str) -> FastAPI:
    """Build the FastAPI app serving the catalog at the given database URL.

    Every route reads the catalog through a connection Postgres itself refuses a write on. The
    curation routes are the one exception, and they reach only a person's own decisions about
    samples, in a schema of their own: what this application records is what a listener decided, and
    the catalog stays the offline pipelines' to build. Morphs are rendered by a separate inference
    process at `inference_url`, which the morph routes reach over HTTP, so the models and the
    libraries behind them stay out of this process.

    Every route is served under `API_PREFIX`, which keeps the whole API inside one path segment
    the single-page application's own routes stay clear of: the frontend reaches `/api/samples`
    while a person's browser holds `/samples/{hash}`, so one path always names one thing.

    A pure factory, deliberately without any module-level instance built from real
    configuration -- that belongs to `sampleserver.main`, the actual ASGI entry point, so that
    importing this module (as tests do, to build an app over a temporary catalog) never depends
    on a real `config.toml` existing. The connections this factory arranges are opened at startup
    rather than at build time, for the same reason.
    """

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Prepare the curation schema and open the inference client before the first request.

        The samples listing reads a sample's hand annotation as part of its own query, and the
        read-only connection every route uses can create nothing. Preparing the schema once at
        startup is what lets a database the offline pipelines have never written to still serve a
        listing. The inference client lives as long as the app, so its connections are reused
        across morph requests, and is closed when the app stops.
        """
        connect_for_curation(application.state.database_url).close()
        application.state.inference_client = build_inference_client(application.state.inference_url)
        try:
            yield
        finally:
            await application.state.inference_client.aclose()

    application = FastAPI(
        title="SampleLibrary",
        description="Read access to the sample catalog, with hand annotation and morphs between samples.",
        lifespan=lifespan,
    )
    application.state.database_url = database_url
    application.state.library_root = library_root
    application.state.inference_url = inference_url
    application.state.spectral_vectors = SpectralVectorCache()
    for api_router in (modules.router, samples.router, stats.router, cloud.router, curation.router, morph.router):
        application.include_router(api_router, prefix=API_PREFIX)
    return application
