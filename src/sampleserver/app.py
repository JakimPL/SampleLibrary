from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from samplecore.storage.database import connect_for_curation
from sampleserver.routers import cloud, curation, modules, samples, stats


def create_app(database_url: str, library_root: Path) -> FastAPI:
    """Build the FastAPI app serving the catalog at the given database URL.

    Every route reads the catalog through a connection Postgres itself refuses a write on. The
    curation routes are the one exception, and they reach only a person's own decisions about
    samples, in a schema of their own: what this application records is what a listener decided, and
    the catalog stays the offline pipelines' to build.

    A pure factory, deliberately without any module-level instance built from real
    configuration -- that belongs to `sampleserver.main`, the actual ASGI entry point, so that
    importing this module (as tests do, to build an app over a temporary catalog) never depends
    on a real `config.toml` existing. The one connection this factory arranges is opened at startup
    rather than at build time, for the same reason.
    """

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Make sure the curation schema exists before the first request reads through it.

        The samples listing reads a sample's hand annotation as part of its own query, and the
        read-only connection every route uses can create nothing. Preparing the schema once at
        startup is what lets a database the offline pipelines have never written to still serve a
        listing.
        """
        connect_for_curation(application.state.database_url).close()
        yield

    application = FastAPI(
        title="SampleLibrary",
        description="Read access to the sample catalog, with hand annotation.",
        lifespan=lifespan,
    )
    application.state.database_url = database_url
    application.state.library_root = library_root
    application.include_router(modules.router)
    application.include_router(samples.router)
    application.include_router(stats.router)
    application.include_router(cloud.router)
    application.include_router(curation.router)
    return application
