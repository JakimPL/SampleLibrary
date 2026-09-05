from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from sampleserver.routers import cloud, modules, samples, stats


def create_app(database_path: Path, library_root: Path) -> FastAPI:
    """Build the read-only FastAPI app serving the catalog at the given database path.

    A pure factory, deliberately without any module-level instance built from real
    configuration -- that belongs to `sampleserver.main`, the actual ASGI entry point, so that
    importing this module (as tests do, to build an app over a temporary catalog) never depends
    on a real `config.toml` existing.
    """
    application = FastAPI(title="SampleLibrary", description="Read-only access to the sample catalog.")
    application.state.database_path = database_path
    application.state.library_root = library_root
    application.include_router(modules.router)
    application.include_router(samples.router)
    application.include_router(stats.router)
    application.include_router(cloud.router)
    return application
