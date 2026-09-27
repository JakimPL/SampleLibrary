from __future__ import annotations

from typing import Final
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, status
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from sampleserver.addresses import is_loopback

LOCAL_HOST_NAMES: Final[frozenset[str]] = frozenset({"localhost", "127.0.0.1", "::1"})
FORWARDING_HEADERS: Final[tuple[str, ...]] = (
    "forwarded",
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
    "x-real-ip",
)
LOCAL_PERSON_DETAIL: Final[str] = "This is only available on the computer SampleLibrary runs on."
POLICY_VIOLATION_CLOSE_CODE: Final[int] = 1008


def is_local_person(connection: HTTPConnection) -> bool:
    """Whether a request comes from a browser on this machine, addressing the server by a local name.

    The connection comes from the loopback address, it names the server by a local name, a page
    that sent it was loaded from a local name, and no proxy forwarded it. A web page from elsewhere
    cannot claim a local origin, a page that renamed its own host to reach this one still names
    that host, and a proxy on this machine announces the address it forwards for.
    """
    client = connection.client
    origin = connection.headers.get("origin")
    return (
        client is not None
        and is_loopback(client.host)
        and connection.url.hostname in LOCAL_HOST_NAMES
        and (origin is None or urlsplit(origin).hostname in LOCAL_HOST_NAMES)
        and not any(header in connection.headers for header in FORWARDING_HEADERS)
    )


def require_local_person(request: Request) -> None:
    """Admit a request only from the person at the machine the server runs on.

    Raises:
        HTTPException: 403 for any request `is_local_person` turns away.
    """
    if not is_local_person(request):
        raise HTTPException(status.HTTP_403_FORBIDDEN, LOCAL_PERSON_DETAIL)


class LocalPersonOnly:
    """Middleware answering the person at this machine alone, on every path the app serves.

    The application a person runs on their own computer lists folders, writes its config file and
    records their labels, so no request from elsewhere reaches any of it, its pages included.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not is_local_person(HTTPConnection(scope)):
            response = JSONResponse({"detail": LOCAL_PERSON_DETAIL}, status_code=status.HTTP_403_FORBIDDEN)
            await response(scope, receive, send)
            return
        if scope["type"] == "websocket" and not is_local_person(HTTPConnection(scope)):
            await send({"type": "websocket.close", "code": POLICY_VIOLATION_CLOSE_CODE})
            return
        await self._app(scope, receive, send)
