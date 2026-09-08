from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from sampleserver.routers import cloud, curation, modules, samples, stats


def create_app(database_url: str, library_root: Path) -> FastAPI:
    """Build the FastAPI app serving the catalog at the given database URL.

    Every route reads the catalog through a connection Postgres itself refuses a write on. The
    curation routes are the one exception, and they reach only a person's own labels, in a schema
    of their own: what this application records is what a listener decided, and the catalog stays
    the offline pipelines' to build.

    A pure factory, deliberately without any module-level instance built from real
    configuration -- that belongs to `sampleserver.main`, the actual ASGI entry point, so that
    importing this module (as tests do, to build an app over a temporary catalog) never depends
    on a real `config.toml` existing.
    """
    application = FastAPI(title="SampleLibrary", description="Read access to the sample catalog, with hand labeling.")
    application.state.database_url = database_url
    application.state.library_root = library_root
    application.include_router(modules.router)
    application.include_router(samples.router)
    application.include_router(stats.router)
    application.include_router(cloud.router)
    application.include_router(curation.router)
    return application
