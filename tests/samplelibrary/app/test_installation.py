from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import httpx
import pytest

from samplelibrary.app.installation import (
    INSTALLATION_ROUTE,
    QUIT_ROUTE,
    Installation,
    PortHolder,
    close_running,
    port_holder,
    this_installation,
)

SETUP_URL: Final[str] = "http://127.0.0.1:8000/api/setup"
QUIT_WAIT_SECONDS: Final[float] = 5.0
SHORT_WAIT_SECONDS: Final[float] = 0.3

Handler = Callable[[httpx.Request], httpx.Response]


def _setup_client(handler: Handler) -> httpx.Client:
    return httpx.Client(base_url=SETUP_URL, transport=httpx.MockTransport(handler))


def _refused(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def _answering(status_code: int, body: object) -> Handler:
    return lambda request: httpx.Response(status_code, json=body)


def _installation(version: str, environment: str) -> dict[str, str]:
    return Installation(version=version, environment=environment).model_dump()


@dataclass(frozen=True)
class HolderCase:
    name: str
    handler: Handler
    expected: PortHolder


HOLDER_CASES: Final[tuple[HolderCase, ...]] = (
    HolderCase("nothing listens", _refused, PortHolder.NOBODY),
    HolderCase("this installation", _answering(200, this_installation().model_dump()), PortHolder.THIS_INSTALLATION),
    HolderCase(
        "another environment",
        _answering(200, _installation(this_installation().version, "/elsewhere")),
        PortHolder.OTHER_INSTALLATION,
    ),
    HolderCase(
        "another version",
        _answering(200, _installation("0.0.0+elsewhere", this_installation().environment)),
        PortHolder.OTHER_INSTALLATION,
    ),
    HolderCase("a page missing", _answering(404, {"detail": "Not Found"}), PortHolder.OTHER_PROGRAM),
    HolderCase("an answer of another shape", _answering(200, {"status": "ok"}), PortHolder.OTHER_PROGRAM),
)


@pytest.mark.parametrize("case", HOLDER_CASES, ids=lambda case: case.name)
def test_a_start_tells_who_holds_its_port(case: HolderCase) -> None:
    with _setup_client(case.handler) as setup:
        assert port_holder(setup) is case.expected


class QuittingApplication:
    """An application of another installation, answering until it has been asked to quit."""

    def __init__(self, *, quits: bool) -> None:
        self.asked_to_quit = False
        self._quits = quits

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.asked_to_quit and self._quits:
            raise httpx.ConnectError("connection refused", request=request)
        if request.method == "POST" and request.url.path.endswith(QUIT_ROUTE):
            self.asked_to_quit = True
            return httpx.Response(202)
        assert request.url.path.endswith(INSTALLATION_ROUTE)
        return httpx.Response(200, json=_installation("0.0.0+elsewhere", "/elsewhere"))


def test_another_installation_is_asked_to_quit_and_its_port_comes_free() -> None:
    application = QuittingApplication(quits=True)
    with _setup_client(application) as setup:
        assert close_running(setup, wait_seconds=QUIT_WAIT_SECONDS)
    assert application.asked_to_quit


def test_an_installation_still_answering_after_the_wait_keeps_its_port() -> None:
    application = QuittingApplication(quits=False)
    with _setup_client(application) as setup:
        assert not close_running(setup, wait_seconds=SHORT_WAIT_SECONDS)
    assert application.asked_to_quit


def test_an_installation_refusing_to_quit_keeps_its_port() -> None:
    with _setup_client(_answering(403, {"detail": "Forbidden"})) as setup:
        assert not close_running(setup, wait_seconds=QUIT_WAIT_SECONDS)
