from __future__ import annotations

from typing import Final
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, status
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from sampleserver.addresses import is_loopback
from sampleserver.policy import ServingPolicy
from sampleserver.request_source import host_of, sent_by_another_site

LOCAL_HOST_NAMES: Final[frozenset[str]] = frozenset({"localhost", "127.0.0.1", "::1"})
FORWARDING_HEADERS: Final[tuple[str, ...]] = (
    "forwarded",
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
    "x-real-ip",
)
LOCAL_PERSON_DETAIL: Final[str] = "This is only available on the computer SampleRipper runs on."
POLICY_VIOLATION_CLOSE_CODE: Final[int] = 1008


def is_local_person(connection: HTTPConnection) -> bool:
    """Whether a request comes from a browser on this machine, addressing the server by a local name.

    The connection comes from the loopback address, its `Host` header names the server by a local
    name, a page that sent it was loaded from a local name, and no proxy forwarded it. A web page
    from elsewhere cannot claim a local origin, sends no request here but a followed link
    (`sampleserver.request_source.sent_by_another_site`), and, having renamed its own host to reach
    this one, still names that host; a proxy on this machine announces the address it forwards for.
    """
    client = connection.client
    origin = connection.headers.get("origin")
    return (
        client is not None
        and is_loopback(client.host)
        and host_of(connection) in LOCAL_HOST_NAMES
        and (origin is None or urlsplit(origin).hostname in LOCAL_HOST_NAMES)
        and not sent_by_another_site(connection)
        and not any(header in connection.headers for header in FORWARDING_HEADERS)
    )


def require_local_person(request: Request) -> None:
    """Admit a request only from the person at the machine the server runs on.

    Raises:
        HTTPException: 403 for any request `is_local_person` turns away.
    """
    if not is_local_person(request):
        raise HTTPException(status.HTTP_403_FORBIDDEN, LOCAL_PERSON_DETAIL)


class LocalPersonOrHomeDevices:
    """Middleware answering the person at this machine on every path, and the devices the policy admits on the others.

    Paths under ``personal_prefix`` list folders, write the config file and quit the application,
    so only the person at this machine reaches them; so do label writes, which the catalog API
    guards itself. Where the policy answers beyond this computer, the devices it admits open the
    library's pages and read its catalog.
    """

    def __init__(self, app: ASGIApp, *, policy: ServingPolicy, personal_prefix: str) -> None:
        self._app = app
        self._policy = policy
        self._personal_prefix = personal_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket") and not self._admitted(HTTPConnection(scope)):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": POLICY_VIOLATION_CLOSE_CODE})
                return
            response = JSONResponse({"detail": LOCAL_PERSON_DETAIL}, status_code=status.HTTP_403_FORBIDDEN)
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)

    def _admitted(self, connection: HTTPConnection) -> bool:
        if is_local_person(connection):
            return True
        path = connection.url.path
        if path == self._personal_prefix or path.startswith(f"{self._personal_prefix}/"):
            return False
        client = connection.client
        host = host_of(connection)
        return (
            self._policy.listens_beyond_this_computer
            and self._policy.admits(client.host if client is not None else None, host)
            and self._policy.admits_page(
                connection.headers.get("origin"), host, from_another_site=sent_by_another_site(connection)
            )
        )
