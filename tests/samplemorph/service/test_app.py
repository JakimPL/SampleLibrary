from __future__ import annotations

from fastapi.testclient import TestClient

from samplemorph.service.app import create_app
from samplemorph.service.settings import ServiceSettings
from tests.samplemorph.service.conftest import load_renderer


def test_the_app_serves_the_renderer_it_was_built_around(settings: ServiceSettings) -> None:
    renderer = load_renderer(settings)

    with TestClient(create_app(renderer)) as client:
        assert client.app.state.renderer is renderer
        assert client.get("/morph/status").json()["fingerprint"] == renderer.fingerprint
