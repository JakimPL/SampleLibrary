from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from samplemorph.service.renderer import load_renderer
from samplemorph.service.routes import router
from samplemorph.service.settings import ServiceSettings


def create_app(settings: ServiceSettings) -> FastAPI:
    """Build the inference app that renders morphs through the route the settings name.

    The models load once, at startup, into the renderer every request shares: a process that
    holds the band matrix's pseudo-inverse and the restorer in memory is what makes a morph a
    fraction of a second rather than the seconds a fresh process spends preparing. A pure factory,
    so a test builds one over a temporary library root with a tiny fitted model.
    """

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Load and warm the renderer before the first request, failing the start when a model is absent."""
        application.state.renderer = load_renderer(settings)
        yield

    application = FastAPI(
        title="SampleLibrary morph inference",
        description="Morphs between two samples of the catalog, rendered through the fitted models.",
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.include_router(router)
    return application
