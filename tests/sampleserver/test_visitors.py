from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import HTTPConnection

from samplecore.config import VisitorLimits
from sampleserver import visitors
from sampleserver.app import API_PREFIX
from sampleserver.dependencies import get_inference_client
from sampleserver.messages import MORPHS_BUSY, TOO_MANY_MORPHS, TOO_MANY_REQUESTS
from sampleserver.visitors import (
    RETRY_AFTER_HEADER,
    UNKNOWN_VISITOR,
    MorphGate,
    TokenBudget,
    VisitorRequestLimits,
    visitor_of,
)
from tests.sampleserver.conftest import INFERENCE_URL, SITE_VISITORS

ADDRESS_HEADER: Final[str] = SITE_VISITORS.address_header
FIRST: Final[str] = "a" * 64
SECOND: Final[str] = "b" * 64
RENDERED: Final[bytes] = b"RIFF...rendered..."
ETAG: Final[str] = '"0123456789abcdef"'


@dataclass
class Clock:
    """A clock a test moves by hand."""

    now: float = 0.0

    def __call__(self) -> float:
        return self.now


@dataclass(frozen=True)
class VisitorCase:
    header: str | None
    peer: str
    visitor: str


VISITOR_CASES: Final[tuple[VisitorCase, ...]] = (
    VisitorCase(header="203.0.113.9", peer="10.0.0.1", visitor="203.0.113.9"),
    VisitorCase(header=None, peer="10.0.0.1", visitor="10.0.0.1"),
    VisitorCase(header="not an address", peer="10.0.0.1", visitor="10.0.0.1"),
    VisitorCase(header="2001:db8:1:2:aaaa::1", peer="10.0.0.1", visitor="2001:db8:1:2::/64"),
    VisitorCase(header="2001:db8:1:2:ffff::9", peer="10.0.0.1", visitor="2001:db8:1:2::/64"),
    VisitorCase(header="::ffff:203.0.113.9", peer="10.0.0.1", visitor="203.0.113.9"),
    VisitorCase(header=None, peer="testclient", visitor=UNKNOWN_VISITOR),
)


def _connection(*, header: str | None, peer: str) -> HTTPConnection:
    headers = [(ADDRESS_HEADER.lower().encode(), header.encode())] if header is not None else []
    return HTTPConnection({"type": "http", "headers": headers, "client": (peer, 50000), "path": "/"})


@pytest.mark.parametrize("case", VISITOR_CASES, ids=lambda case: f"{case.header} from {case.peer}")
def test_a_visitor_is_the_address_the_platform_names_and_a_host_counts_by_its_network(case: VisitorCase) -> None:
    assert visitor_of(_connection(header=case.header, peer=case.peer), address_header=ADDRESS_HEADER) == case.visitor


def test_a_budget_spends_down_and_refills_with_time() -> None:
    clock = Clock()
    budget = TokenBudget(capacity=3.0, refill_per_second=1.0, clock=clock)

    spent = [budget.take("visitor", 1.0) for _ in range(3)]
    refused = budget.take("visitor", 1.0)
    clock.now = 2.0

    assert spent == [None, None, None]
    assert refused == pytest.approx(1.0)
    assert budget.take("visitor", 2.0) is None


def test_a_budget_charged_after_the_fact_goes_into_debt() -> None:
    clock = Clock()
    budget = TokenBudget(capacity=1.0, refill_per_second=1.0, clock=clock)

    budget.charge("visitor", 2.0)

    assert budget.take("visitor", 1.0) == pytest.approx(2.0)


def test_a_budget_holds_a_bounded_number_of_visitors(monkeypatch: pytest.MonkeyPatch) -> None:
    """A flood of addresses forgets the idlest visitor, who then starts again with a full budget."""
    monkeypatch.setattr(visitors, "MAXIMUM_TRACKED_VISITORS", 2)
    budget = TokenBudget(capacity=1.0, refill_per_second=0.001, clock=Clock())
    budget.take("first", 1.0)
    budget.take("second", 1.0)

    budget.take("third", 1.0)

    assert budget.take("second", 1.0) is not None
    assert budget.take("first", 1.0) is None


def _limited(limits: VisitorLimits, clock: Clock) -> FastAPI:
    application = FastAPI()

    @application.get(f"{API_PREFIX}/stats")
    def stats() -> dict[str, int]:
        return {"module_count": 0}

    @application.get(f"{API_PREFIX}/samples/{{sample_hash}}")
    def sample(sample_hash: str) -> dict[str, str]:
        return {"hash": sample_hash}

    @application.get(f"{API_PREFIX}/health")
    def health() -> dict[str, bool]:
        return {"catalog_answers": True}

    application.add_middleware(VisitorRequestLimits, limits=limits, api_prefix=API_PREFIX, clock=clock)
    return application


def test_a_visitor_past_the_request_budget_is_told_when_to_ask_again() -> None:
    limits = SITE_VISITORS.model_copy(update={"burst": 3, "refill_per_second": 1.0})
    with TestClient(_limited(limits, Clock())) as client:
        answers = [
            client.get(f"{API_PREFIX}/samples/{FIRST}", headers={ADDRESS_HEADER: "203.0.113.9"}) for _ in range(4)
        ]
        elsewhere = client.get(f"{API_PREFIX}/samples/{FIRST}", headers={ADDRESS_HEADER: "203.0.113.10"})

    assert [answer.status_code for answer in answers] == [200, 200, 200, 429]
    assert answers[-1].json() == {"detail": TOO_MANY_REQUESTS}
    assert answers[-1].headers[RETRY_AFTER_HEADER] == "1"
    assert elsewhere.status_code == 200


def test_a_whole_catalog_answer_costs_its_weight_and_the_health_check_costs_nothing() -> None:
    limits = SITE_VISITORS.model_copy(update={"burst": 5, "refill_per_second": 1.0, "whole_catalog_weight": 5})
    with TestClient(_limited(limits, Clock())) as client:
        whole = client.get(f"{API_PREFIX}/stats")
        health = [client.get(f"{API_PREFIX}/health").status_code for _ in range(10)]
        after = client.get(f"{API_PREFIX}/samples/{FIRST}")

    assert whole.status_code == 200
    assert set(health) == {200}
    assert after.status_code == 429


def test_the_gate_spends_one_morph_of_the_visitors_budget_and_everyones() -> None:
    clock = Clock()
    limits = SITE_VISITORS.model_copy(update={"morphs_per_minute": 1, "morphs_per_minute_overall": 2})
    gate = MorphGate(concurrent=limits.concurrent_morphs, limits=limits, clock=clock)

    gate.admit("first")
    with pytest.raises(HTTPException, match=TOO_MANY_MORPHS):
        gate.admit("first")
    gate.admit("second")
    with pytest.raises(HTTPException, match=TOO_MANY_MORPHS):
        gate.admit("third")


def test_a_gate_without_visitor_limits_charges_no_budget() -> None:
    gate = MorphGate(concurrent=1, limits=None, clock=Clock())

    for _ in range(SITE_VISITORS.morphs_per_minute_overall + 1):
        gate.admit("192.168.1.20")


def test_the_gate_holds_as_many_renders_as_it_may_and_turns_the_next_away() -> None:
    gate = MorphGate(concurrent=1, limits=None, clock=Clock())

    with gate.slot():
        with pytest.raises(HTTPException, match=MORPHS_BUSY):
            with gate.slot():
                pass
    with gate.slot():
        pass


@dataclass
class Renderer:
    """A stand-in renderer answering 304 to a request naming the render it made, and counting what it rendered."""

    rendered: list[httpx.Request] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("if-none-match") == ETAG:
            return httpx.Response(304, headers={"etag": ETAG})
        self.rendered.append(request)
        return httpx.Response(200, content=RENDERED, headers={"content-type": "audio/wav", "etag": ETAG})


def test_a_site_charges_a_visitor_for_new_renders_alone(public_client: TestClient) -> None:
    """The waveform asks again for the render the player already holds, which the renderer confirms for free."""
    renderer = Renderer()
    mock_client = httpx.AsyncClient(base_url=INFERENCE_URL, transport=httpx.MockTransport(renderer))
    public_client.app.dependency_overrides[get_inference_client] = lambda: mock_client
    point = {"first": FIRST, "second": SECOND, "weight": 0.5}
    visitor = {ADDRESS_HEADER: "203.0.113.9"}

    confirmed = [
        public_client.get("/morph/audio", params=point, headers={**visitor, "if-none-match": ETAG}).status_code
        for _ in range(5)
    ]
    rendered = [
        public_client.get("/morph/audio", params={**point, "weight": weight}, headers=visitor).status_code
        for weight in (0.25, 0.5, 0.75, 1.0)
    ]

    assert set(confirmed) == {304}
    assert rendered == [200, 200, 200, 429]
    assert len(renderer.rendered) == SITE_VISITORS.morphs_per_minute


def test_a_cloud_answer_a_browser_holds_is_confirmed_with_no_body(client: TestClient) -> None:
    first = client.get("/cloud")

    again = client.get("/cloud", headers={"if-none-match": first.headers["etag"]})

    assert first.status_code == 200
    assert (again.status_code, again.content) == (304, b"")
    assert again.headers["etag"] == first.headers["etag"]
