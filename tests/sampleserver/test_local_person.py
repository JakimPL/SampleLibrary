from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from samplecore.config import DEFAULT_SERVER_CONFIG, Exposure, ServerConfig
from sampleserver.local_person import LocalPersonOrHomeDevices
from sampleserver.policy import ServingPolicy

LOCAL_CLIENT: Final[tuple[str, int]] = ("127.0.0.1", 50000)
LOCAL_BASE_URL: Final[str] = "http://localhost"
HOME_DEVICE: Final[tuple[str, int]] = ("192.168.1.20", 50000)
HOME_BASE_URL: Final[str] = "http://192.168.1.10"
PERSONAL_PREFIX: Final[str] = "/personal"
LOCAL_POLICY: Final[ServingPolicy] = ServingPolicy.of(DEFAULT_SERVER_CONFIG)
NETWORK_POLICY: Final[ServingPolicy] = ServingPolicy.of(ServerConfig(exposure=Exposure.NETWORK))


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
    RequestCase("a rebound name a URL parser rejects", admitted=False, headers={"host": "a_b.attacker.example:27440"}),
    RequestCase(
        "an element on another site's page",
        admitted=False,
        headers={"sec-fetch-site": "cross-site", "sec-fetch-mode": "no-cors"},
    ),
    RequestCase(
        "a link followed from another site",
        admitted=True,
        headers={"sec-fetch-site": "cross-site", "sec-fetch-mode": "navigate"},
    ),
)


def _guarded_application(policy: ServingPolicy) -> FastAPI:
    application = FastAPI()
    application.add_middleware(LocalPersonOrHomeDevices, policy=policy, personal_prefix=PERSONAL_PREFIX)

    @application.get("/page")
    def page() -> dict[str, bool]:
        return {"served": True}

    @application.get(f"{PERSONAL_PREFIX}/folders")
    def folders() -> dict[str, bool]:
        return {"served": True}

    return application


@pytest.mark.parametrize("case", REQUEST_CASES, ids=lambda case: case.name)
def test_only_the_person_at_this_machine_is_answered(case: RequestCase) -> None:
    with TestClient(_guarded_application(LOCAL_POLICY), base_url=case.base_url, client=case.client) as client:
        response = client.get("/page", headers=case.headers)

    assert response.status_code == (200 if case.admitted else 403)


HOME_CASES: Final[tuple[RequestCase, ...]] = (
    RequestCase("a device at home", admitted=True, client=HOME_DEVICE, base_url=HOME_BASE_URL),
    RequestCase(
        "a page it loaded from here",
        admitted=True,
        client=HOME_DEVICE,
        base_url=HOME_BASE_URL,
        headers={"origin": HOME_BASE_URL},
    ),
    RequestCase(
        "a page from elsewhere",
        admitted=False,
        client=HOME_DEVICE,
        base_url=HOME_BASE_URL,
        headers={"origin": "http://attacker.example"},
    ),
    RequestCase(
        "a name another site points here", admitted=False, client=HOME_DEVICE, base_url="http://rebound.example"
    ),
    RequestCase("an address beyond the home", admitted=False, client=("203.0.113.9", 50000), base_url=HOME_BASE_URL),
    RequestCase(
        "a rebound name a URL parser rejects",
        admitted=False,
        client=HOME_DEVICE,
        base_url=HOME_BASE_URL,
        headers={"host": "a_b.attacker.example:27440"},
    ),
    RequestCase(
        "an element on another site's page",
        admitted=False,
        client=HOME_DEVICE,
        base_url=HOME_BASE_URL,
        headers={"sec-fetch-site": "cross-site", "sec-fetch-mode": "no-cors"},
    ),
)


@pytest.mark.parametrize("case", HOME_CASES, ids=lambda case: case.name)
def test_a_home_network_opens_to_its_own_devices(case: RequestCase) -> None:
    with TestClient(_guarded_application(NETWORK_POLICY), base_url=case.base_url, client=case.client) as client:
        response = client.get("/page", headers=case.headers)

    assert response.status_code == (200 if case.admitted else 403)


def test_the_personal_paths_answer_the_person_at_this_machine_alone() -> None:
    application = _guarded_application(NETWORK_POLICY)
    with TestClient(application, base_url=HOME_BASE_URL, client=HOME_DEVICE) as device:
        assert device.get(f"{PERSONAL_PREFIX}/folders").status_code == 403
    with TestClient(application, base_url=LOCAL_BASE_URL, client=LOCAL_CLIENT) as person:
        assert person.get(f"{PERSONAL_PREFIX}/folders").status_code == 200
