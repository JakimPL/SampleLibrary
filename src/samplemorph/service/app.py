from __future__ import annotations

from fastapi import FastAPI

from samplemorph.service.renderer import MorphRenderer
from samplemorph.service.routes import router


def create_app(renderer: MorphRenderer) -> FastAPI:
    """Build the inference app around a renderer already loaded and warmed.

    The route is built and warmed once, before the app exists, into the renderer every request
    shares, so the first morph costs what any later one does. A pure factory, so a test builds one
    over a renderer loaded from a temporary library root.
    """
    application = FastAPI(
        title="SampleLibrary morph inference",
        description="Morphs between two samples of the catalog, rendered through the envelope route.",
    )
    application.state.renderer = renderer
    application.include_router(router)
    return application
