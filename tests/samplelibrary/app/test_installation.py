from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import httpx
import pytest

from samplelibrary.app.installation import QUIT_ROUTE, Installation, Reply, ask_to_quit, reply_at, this_installation

SETUP_URL: Final[str] = "http://127.0.0.1:27440/api/setup"
QUIT_SECONDS: Final[float] = 5.0

Handler = Callable[[httpx.Request], httpx.Response]


def _setup_client(handler: Handler) -> httpx.Client:
    return httpx.Client(base_url=SETUP_URL, transport=httpx.MockTransport(handler))


def _raising(error: type[httpx.TransportError]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error("no answer", request=request)

    return handler


def _answering(status_code: int, body: object) -> Handler:
    return lambda request: httpx.Response(status_code, json=body)


def _installation(version: str, environment: str) -> dict[str, str]:
    return Installation(version=version, environment=environment).model_dump()


@dataclass(frozen=True)
class ReplyCase:
    name: str
    handler: Handler
    expected: Reply


REPLY_CASES: Final[tuple[ReplyCase, ...]] = (
    ReplyCase("a refused connection", _raising(httpx.ConnectError), Reply.CLOSED),
    ReplyCase("a dropped connection", _raising(httpx.RemoteProtocolError), Reply.CLOSED),
    ReplyCase("a connection left unanswered", _raising(httpx.ReadTimeout), Reply.SILENT),
    ReplyCase("a connection never taken", _raising(httpx.ConnectTimeout), Reply.SILENT),
    ReplyCase("this installation", _answering(200, this_installation().model_dump()), Reply.SAME_INSTALLATION),
    ReplyCase(
        "another environment",
        _answering(200, _installation(this_installation().version, "/elsewhere")),
        Reply.OTHER_INSTALLATION,
    ),
    ReplyCase(
        "another version",
        _answering(200, _installation("0.0.0+elsewhere", this_installation().environment)),
        Reply.OTHER_INSTALLATION,
    ),
    ReplyCase("a version without the route", _answering(404, {"detail": "Not Found"}), Reply.OTHER_INSTALLATION),
    ReplyCase("an answer of another shape", _answering(200, {"status": "ok"}), Reply.OTHER_INSTALLATION),
)


@pytest.mark.parametrize("case", REPLY_CASES, ids=lambda case: case.name)
def test_a_start_tells_how_the_running_application_answers(case: ReplyCase) -> None:
    with _setup_client(case.handler) as setup:
        assert reply_at(setup) is case.expected


def test_a_running_application_is_asked_to_quit() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(f"{request.method} {request.url.path}")
        return httpx.Response(202)

    with _setup_client(handler) as setup:
        ask_to_quit(setup, seconds=QUIT_SECONDS)

    assert requests == [f"POST /api/setup{QUIT_ROUTE}"]


@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.RemoteProtocolError], ids=("unanswered", "dropped"))
def test_a_quit_the_application_leaves_unanswered_is_left_to_its_lock(error: type[httpx.TransportError]) -> None:
    with _setup_client(_raising(error)) as setup:
        ask_to_quit(setup, seconds=QUIT_SECONDS)
