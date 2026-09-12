from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
import pytest
from fastapi.testclient import TestClient

from sampleserver.dependencies import get_inference_client
from tests.sampleserver.conftest import INFERENCE_URL

FIRST = "a" * 64
SECOND = "b" * 64
RENDERED = b"RIFF...rendered..."
ETAG = '"0123456789abcdef"'
CACHE_CONTROL = "private, max-age=3600"
STATUS = {
    "model": "principal_components",
    "codec": "principal_components",
    "canonicalizer": "log_frequency",
    "latent_size": 256,
    "vocoder": "restored",
    "restorer": "restorer",
    "device": "cpu",
    "fingerprint": "f" * 64,
    "weight_steps": 16,
}

Handler = Callable[[httpx.Request], httpx.Response]


@dataclass
class Upstream:
    """A stand-in inference process: what it answers, and every request it received."""

    handler: Handler
    requests: list[httpx.Request] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def _serve(client: TestClient, handler: Handler) -> Upstream:
    upstream = Upstream(handler)
    mock_client = httpx.AsyncClient(base_url=INFERENCE_URL, transport=httpx.MockTransport(upstream))
    client.app.dependency_overrides[get_inference_client] = lambda: mock_client
    return upstream


def _rendered(request: httpx.Request) -> httpx.Response:
    if request.headers.get("if-none-match") == ETAG:
        return httpx.Response(304, headers={"etag": ETAG, "cache-control": CACHE_CONTROL})
    return httpx.Response(
        200, content=RENDERED, headers={"content-type": "audio/wav", "etag": ETAG, "cache-control": CACHE_CONTROL}
    )


def _refusing(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def test_a_render_is_relayed_with_its_caching_headers(client: TestClient) -> None:
    upstream = _serve(client, _rendered)

    response = client.get("/morph/audio", params={"first": FIRST, "second": SECOND, "weight": 0.5})

    assert response.status_code == 200
    assert response.content == RENDERED
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["etag"] == ETAG
    assert response.headers["cache-control"] == CACHE_CONTROL
    assert upstream.requests[0].url.path == "/morph/audio"
    assert dict(upstream.requests[0].url.params) == {"first": FIRST, "second": SECOND, "weight": "0.5"}


def test_a_caller_s_validator_is_forwarded_and_the_process_s_304_comes_back(client: TestClient) -> None:
    _serve(client, _rendered)

    response = client.get(
        "/morph/audio", params={"first": FIRST, "second": SECOND, "weight": 0.5}, headers={"If-None-Match": ETAG}
    )

    assert response.status_code == 304
    assert response.headers["etag"] == ETAG


def test_no_process_answering_reads_as_unavailable(client: TestClient) -> None:
    _serve(client, _refusing)

    audio = client.get("/morph/audio", params={"first": FIRST, "second": SECOND, "weight": 0.5})
    status = client.get("/morph/status")

    assert audio.status_code == 503
    assert INFERENCE_URL in audio.json()["detail"]
    assert status.json() == {"available": False, "service": None}


def test_the_process_s_own_refusals_are_relayed_with_their_detail(client: TestClient) -> None:
    _serve(client, lambda request: httpx.Response(404, json={"detail": "no object is stored for sample " + SECOND}))

    response = client.get("/morph/audio", params={"first": FIRST, "second": SECOND, "weight": 0.5})

    assert response.status_code == 404
    assert response.json()["detail"].startswith("no object is stored")


@pytest.mark.parametrize("weight", (0.3, 2.0))
def test_a_weight_off_the_grid_is_refused_before_the_process_is_dialed(client: TestClient, weight: float) -> None:
    upstream = _serve(client, _rendered)

    response = client.get("/morph/audio", params={"first": FIRST, "second": SECOND, "weight": weight})

    assert response.status_code == 422
    assert upstream.requests == []


def test_the_status_carries_what_the_process_serves(client: TestClient) -> None:
    _serve(client, lambda request: httpx.Response(200, json=STATUS))

    response = client.get("/morph/status")

    assert response.json() == {"available": True, "service": STATUS}
