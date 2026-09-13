from __future__ import annotations

from fastapi import Request

from samplemorph.service.renderer import MorphRenderer


def get_renderer(request: Request) -> MorphRenderer:
    """The one renderer this process loaded at startup, shared by every request."""
    renderer: MorphRenderer = request.app.state.renderer
    return renderer
