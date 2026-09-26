from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sampleserver.local_person import LocalPersonOnly

LOCAL_CLIENT: Final[tuple[str, int]] = ("127.0.0.1", 50000)
LOCAL_BASE_URL: Final[str] = "http://localhost"


@dataclass(frozen=True)
class RequestCase:
    name: str
    admitted: bool
    client: tuple[str, int] = LOCAL_CLIENT
    base_url: str = LOCAL_BASE_URL
    headers: dict[str, str] = field(default_factory=dict)


REQUEST_CASES: Final[tuple[RequestCase, ...]] = (
    RequestCase("a browser on this machine", admitted=True),
    RequestCase("a page from this machine", admitted=True, headers={"origin": "http://localhost:5173"}),
    RequestCase("the IPv6 loopback address", admitted=True, client=("::1", 50000)),
    RequestCase("another machine", admitted=False, client=("192.168.1.20", 50000)),
    RequestCase("a name another site points here", admitted=False, base_url="http://attacker.example"),
    RequestCase("a page from elsewhere", admitted=False, headers={"origin": "http://attacker.example"}),
    RequestCase("a proxy forwarding for another machine", admitted=False, headers={"x-forwarded-for": "203.0.113.9"}),
    RequestCase("a proxy naming the forwarded request", admitted=False, headers={"forwarded": "for=203.0.113.9"}),
    RequestCase("a proxy passing the real address", admitted=False, headers={"x-real-ip": "203.0.113.9"}),
)


def _guarded_application() -> FastAPI:
    application = FastAPI()
    application.add_middleware(LocalPersonOnly)

    @application.get("/page")
    def page() -> dict[str, bool]:
        return {"served": True}

    return application


@pytest.mark.parametrize("case", REQUEST_CASES, ids=lambda case: case.name)
def test_only_the_person_at_this_machine_is_answered(case: RequestCase) -> None:
    with TestClient(_guarded_application(), base_url=case.base_url, client=case.client) as client:
        response = client.get("/page", headers=case.headers)

    assert response.status_code == (200 if case.admitted else 403)
