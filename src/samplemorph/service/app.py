from __future__ import annotations

from fastapi import FastAPI

from samplemorph.service.callers import ProgramsCallingItsAddressOnly
from samplemorph.service.renderer import MorphRenderer
from samplemorph.service.routes import router


def create_app(renderer: MorphRenderer, *, host: str) -> FastAPI:
    """Build the inference app around a renderer already loaded and warmed, answering calls to ``host`` from programs.

    The route is built and warmed once, before the app exists, into the renderer every request
    shares, so the first morph costs what any later one does. The app answers the catalog API and
    a sampler calling it by the address it listens on, or by a loopback name, and no web page
    (`samplemorph.service.callers`). A pure factory, so a test builds one over a renderer loaded from
    a temporary library root.
    """
    application = FastAPI(
        title="SampleRipper morph inference",
        description="Morphs between two samples of the catalog, rendered through the envelope route.",
    )
    application.add_middleware(ProgramsCallingItsAddressOnly, host=host)
    application.state.renderer = renderer
    application.include_router(router)
    return application
