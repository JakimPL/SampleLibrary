from __future__ import annotations

from fastapi import FastAPI

from samplemorph.service.renderer import MorphRenderer
from samplemorph.service.routes import router


def create_app(renderer: MorphRenderer) -> FastAPI:
    """Build the inference app around a renderer already loaded and warmed.

    The models load once, before the app exists, into the renderer every request shares: a process
    that holds the band matrix's pseudo-inverse and the restorer in memory is what makes a morph a
    fraction of a second rather than the seconds a fresh process spends preparing, and a model that
    fails to load ends the process before it binds an address. A pure factory, so a test builds
    one over a renderer loaded from a temporary library root.
    """
    application = FastAPI(
        title="SampleLibrary morph inference",
        description="Morphs between two samples of the catalog, rendered through the fitted models.",
    )
    application.state.renderer = renderer
    application.include_router(router)
    return application
